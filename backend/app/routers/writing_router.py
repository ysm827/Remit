"""论文工作区 API；写作任务与建模任务有独立状态和生命周期。"""

import asyncio
import io
import json
import re
import shutil
import zipfile
from functools import partial as bind
from threading import Event
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.config.setting import settings
from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.core.paper_mode import PaperMode, short_config
from app.routers.files_router import _resolve_task_directory
from app.services import writing_workspace as workspace
from app.services.team_state import compiling_tasks
from app.services.async_io import run_blocking, run_cancellable, WorkCancelled

router = APIRouter(prefix="/api/writing", tags=["writing"])
_locks: dict[str, asyncio.Lock] = {}
_generations: dict[str, asyncio.Task] = {}
_compiling = compiling_tasks
_compile_cancel: dict[str, Event] = {}
_compile_jobs: dict[str, asyncio.Task] = {}


async def shutdown_writers() -> None:
    """退出服务前停止论文任务并保存中断状态。"""
    active = list(set(_generations.values()) | set(_compile_jobs.values()))
    for signal in _compile_cancel.values():
        signal.set()
    for task in active:
        if not task.cancelling():
            task.cancel()
    if active:
        await asyncio.gather(*active, return_exceptions=True)


def _lock(task_id: str) -> asyncio.Lock:
    return _locks.setdefault(task_id, asyncio.Lock())


def _root(task_id: str) -> Path:
    return workspace.ensure_workspace(_resolve_task_directory(task_id))


def _meta(root: Path) -> dict:
    return workspace.read_json(root / "workspace.json")


def _set_generation(root: Path, status: str, **fields) -> None:
    meta = _meta(root)
    previous = meta.get("generation", {})
    identity = {
        k: previous[k]
        for k in (
            "generation_id",
            "input_revision",
            "plan_revision",
            "mode",
            "file",
            "partial",
            "completed_sections",
            "follow_draft",
            "base_generation_id",
            "revised_sections",
            "proposal_id",
        )
        if k in previous
    }
    if fields.get("generation_id", previous.get("generation_id")) != previous.get(
        "generation_id"
    ):
        identity = {}
    meta["generation"] = {**identity, "status": status, "at": workspace.now(), **fields}
    workspace.write_json(root / "workspace.json", meta)
    from app.services.team_state import record

    record(
        root.parent,
        "writer",
        "writing",
        f"论文手 · {fields.get('section') or status}",
        meta["generation"],
    )


@router.get("/projects")
async def projects() -> list[dict]:
    """列出已建模项目及独立论文的就绪状态。"""

    def collect() -> list[dict]:
        result = []
        for path in Path("project/work_dir").glob("*/workflow_state.json"):
            try:
                state = workspace.read_json(path)
                paper = workspace.paper_root(path.parent)
                inputs = workspace.read_json(paper / "input.json")
                result.append(
                    {
                        "task_id": path.parent.name,
                        "title": str(
                            (state.get("questions") or {}).get("title")
                            or (state.get("problem") or {}).get("ques_all")
                            or path.parent.name
                        )[:100],
                        "status": state.get("status"),
                        "updated_at": state.get("updated_at"),
                        "ready": state.get("status") == "completed",
                        "synced_at": inputs.get("synced_at"),
                        "sections": len((state.get("solution_results") or {})),
                    }
                )
            except (ValueError, OSError):
                continue
        return sorted(
            result, key=lambda item: item.get("updated_at") or "", reverse=True
        )

    return await asyncio.to_thread(collect)


@router.get("/{task_id}")
async def get_workspace(task_id: str) -> dict:
    """读取工作区清单，兼容迁入已完成的旧项目。"""
    async with _lock(task_id):
        root = _root(task_id)
        state = workspace.read_json(root.parent / "workflow_state.json")
        if state.get("status") == "completed" and not (root / "input.json").is_file():
            await asyncio.to_thread(workspace.sync_results, root.parent, state)
        meta = _meta(root)
        if (
            meta.get("generation", {}).get("status") in {"running", "stopping"}
            and task_id not in _generations
        ):
            _set_generation(
                root, "interrupted", error="服务已重启，上次写作中断。可重新生成。"
            )
            meta = _meta(root)
        compile_result = workspace.read_json(root / "compile.json")
        if (
            compile_result.get("status") in {"running", "stopping"}
            and task_id not in _compiling
        ):
            compile_result = {
                **compile_result,
                "status": "interrupted",
                "log": "服务已重启，上次编译中断；上次成功的 PDF 仍保留，可重新编译。",
            }
            workspace.write_json(root / "compile.json", compile_result)
        return {
            **meta,
            "mode": meta.get("mode", "full_paper"),
            "mode_version": meta.get("mode_version", "legacy"),
            "document_mode": workspace.document_mode(root),
            "task_id": task_id,
            "modeling_status": state.get("status"),
            "ready": state.get("status") == "completed",
            "inputs": workspace.read_json(root / "input.json"),
            "revision": await asyncio.to_thread(workspace.project_revision, root),
            "files": [
                {
                    "name": path.relative_to(root).as_posix(),
                    "editable": path.suffix.lower() in workspace.EDITABLE,
                }
                for path in workspace.source_files(root)
            ],
            "compile": compile_result,
            "compiling": task_id in _compiling,
            "pdf_available": (root / "preview.pdf").is_file(),
        }


@router.post("/{task_id}/sync")
async def sync(task_id: str) -> dict:
    """显式刷新素材快照；重跑期间不能导入未通过验收的结果。"""
    async with _lock(task_id):
        root = _root(task_id)
        state = WorkflowCheckpoint(root.parent).load()
        if state.get("status") != "completed":
            raise HTTPException(409, "请先完成建模流程及节点验收，再同步论文素材")
        return await asyncio.to_thread(workspace.sync_results, root.parent, state)


@router.get("/{task_id}/source")
async def source(task_id: str, name: str = "main.tex") -> dict:
    """读取一个可编辑文件及保存版本。"""
    try:
        path = workspace.resolve_source(_root(task_id), name)
        if not path.is_file():
            raise HTTPException(404, "源码文件不存在")
        content = path.read_text(encoding="utf-8")
        return {"name": name, "content": content, "version": workspace.digest(content)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class SaveSource(BaseModel):
    """期望版本为空只允许创建文件。"""

    name: str = Field(max_length=200)
    content: str = Field(max_length=2 * 1024 * 1024)
    version: str | None = None


@router.post("/{task_id}/source")
async def save(task_id: str, body: SaveSource) -> dict:
    """冲突返回 409，客户端必须保留未保存编辑。"""
    async with _lock(task_id):
        try:
            root = _root(task_id)
            version = workspace.save_source(root, body.name, body.content, body.version)
            return {"version": version, "revision": workspace.project_revision(root)}
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


class MainFile(BaseModel):
    name: str


class WritingMode(BaseModel):
    mode: PaperMode
    version: str


@router.put("/{task_id}/mode")
async def set_mode(task_id: str, body: WritingMode) -> dict:
    """Set the next draft's purpose without relabelling existing source/PDF."""
    async with _lock(task_id):
        root = _root(task_id)
        if task_id in _generations or task_id in _compiling:
            raise HTTPException(409, "请等待或停止当前写作和编译后再切换模式。")
        meta = _meta(root)
        if body.version != meta.get("mode_version", "legacy"):
            raise HTTPException(409, "写作模式已被其他窗口修改，请刷新后重试。")
        meta.update(mode=body.mode, mode_version=uuid4().hex)
        workspace.write_json(root / "workspace.json", meta)
        return {"mode": meta["mode"], "mode_version": meta["mode_version"]}


@router.post("/{task_id}/main")
async def set_main(task_id: str, body: MainFile) -> dict:
    """选择编译入口，不移动或覆盖源码。"""
    async with _lock(task_id):
        root = _root(task_id)
        try:
            path = workspace.resolve_source(root, body.name)
            if not path.is_file() or path.suffix != ".tex":
                raise ValueError("主文件必须是已存在的 .tex 文件")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _meta(root)
        meta["main"] = body.name
        workspace.write_json(root / "workspace.json", meta)
        return {"main": body.name}


@router.post("/{task_id}/compile")
async def compile_source(task_id: str) -> dict:
    """编译输入快照；失败保留上次成功的 PDF。"""
    async with _lock(task_id):
        if task_id in _compiling:
            raise HTTPException(409, "该项目正在编译")
        root = _root(task_id)
        build, main, revision = await run_blocking(workspace.prepare_build, root)
        signal = Event()
        previous = workspace.read_json(root / "compile.json")
        workspace.write_json(
            root / "compile.json",
            {**previous, "status": "running", "revision": revision},
        )
        from app.services.team_state import record

        record(
            root.parent, "writer", "compile", "开始编译 LaTeX", {"status": "running"}
        )
        _compiling.add(task_id)
        _compile_cancel[task_id] = signal
        _compile_jobs[task_id] = asyncio.current_task()
    try:
        from app.services.call_ledger import scope as call_scope

        with call_scope(task_id, run_id=uuid4().hex, stage_id="paper:compile"):
            result = await run_cancellable(
                workspace.compile_build, build, main, revision, cancel_event=signal
            )
        async with _lock(task_id):
            if signal.is_set():
                raise WorkCancelled("编译已停止")
            previous = workspace.read_json(root / "compile.json")
            if result["status"] == "completed":
                import pymupdf

                temp = root / "preview.pdf.tmp"
                shutil.copy2(build / "preview.pdf", temp)
                temp.replace(root / "preview.pdf")
                pdf_version = root / ".pdf" / f"{revision}.pdf"
                pdf_version.parent.mkdir(exist_ok=True)
                shutil.copy2(root / "preview.pdf", pdf_version)
                with pymupdf.open(pdf_version) as document:
                    result["page_count"] = len(document)
                result["pdf_revision"] = revision
                result["pdf_mode"] = result.get("mode", "full_paper")
            else:
                result["pdf_revision"] = previous.get("pdf_revision")
                result["page_count"] = previous.get("page_count", 0)
                result["pdf_mode"] = previous.get("pdf_mode", "full_paper")
            workspace.write_json(root / "compile.json", result)
        record(
            root.parent,
            "writer",
            "compile",
            "PDF 编译完成" if result["status"] == "completed" else "PDF 编译失败",
            {"status": result["status"]},
        )
        await asyncio.to_thread(workspace.trim_build_cache, root)
        return result
    except (WorkCancelled, asyncio.CancelledError) as exc:
        # No await here: the worker has already exited, and this event-loop turn
        # persists cancellation before releasing this project's compile ownership.
        result = {
            "status": "cancelled",
            "revision": revision,
            "at": workspace.now(),
            "pdf_revision": previous.get("pdf_revision"),
            "pdf_mode": previous.get("pdf_mode", "full_paper"),
            "page_count": previous.get("page_count", 0),
            "log": "编译已停止，源码和上次成功的 PDF 已保留。",
            "diagnostics": [],
        }
        workspace.write_json(root / "compile.json", result)
        record(root.parent, "writer", "compile", result["log"], {"status": "cancelled"})
        if isinstance(exc, asyncio.CancelledError):
            raise
        return result
    except Exception as exc:
        workspace.write_json(
            root / "compile.json",
            {**previous, "status": "failed", "log": "编译中断，请查看服务日志。"},
        )
        record(root.parent, "writer", "error", f"编译中断：{str(exc)[:300]}")
        raise
    finally:
        _compiling.discard(task_id)
        _compile_cancel.pop(task_id, None)
        _compile_jobs.pop(task_id, None)


@router.get("/{task_id}/pdf")
async def pdf(task_id: str) -> FileResponse:
    """显示最后一次成功编译的 PDF。"""
    path = _root(task_id) / "preview.pdf"
    if not path.is_file():
        raise HTTPException(404, "尚未成功编译 PDF")
    return FileResponse(
        path, media_type="application/pdf", headers={"Cache-Control": "no-cache"}
    )


@router.get("/{task_id}/pdf/pages/{page}")
async def pdf_page(
    task_id: str, page: int, revision: str, scale: float = 1.5
) -> Response:
    """从已编译 PDF 渲染页面，桌面 WebView 不依赖浏览器 PDF 插件。"""
    if not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise HTTPException(400, "无效 PDF 版本")
    path = _root(task_id) / ".pdf" / f"{revision}.pdf"
    if not path.is_file():
        raise HTTPException(404, "PDF 版本不存在，请重新编译")

    def render() -> bytes:
        import pymupdf

        with pymupdf.open(path) as document:
            if page < 0 or page >= len(document):
                raise HTTPException(404, "页码超出范围")
            current = document[page]
            zoom = max(
                0.5,
                min(4.0, scale, 4608 / max(current.rect.width, current.rect.height)),
            )
            return current.get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom), alpha=False
            ).tobytes("png")

    image = await asyncio.to_thread(render)
    return Response(
        image,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/{task_id}/export")
async def export(task_id: str) -> Response:
    """下载可在其他 LaTeX 编辑器打开的项目。"""
    async with _lock(task_id):
        root = _root(task_id)
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            from app.services.competitions import export_notes

            meta = _meta(root)
            compiled = workspace.read_json(root / "compile.json")
            archive.writestr(
                "document.json",
                json.dumps(
                    {
                        "main": meta.get("main", "main.tex"),
                        "mode": workspace.document_mode(root),
                        "document_modes": meta.get("document_modes", {}),
                        "source_revision": workspace.project_revision(root),
                        "pdf_revision": compiled.get("pdf_revision"),
                        "pdf_mode": compiled.get("pdf_mode", "full_paper")
                        if (root / "preview.pdf").exists()
                        else None,
                        "submission_verified": False,
                        "task_purpose": (
                            workspace.read_json(
                                root.parent / "workflow_state.json"
                            ).get("problem")
                            or {}
                        ).get("task_purpose", "modeling"),
                        "note": "短报告用于说明现有结果；完整论文也须按赛事要求和科学证据核验后提交。",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            for name, content in export_notes(root.parent).items():
                archive.writestr(name, content)
            for path in workspace.source_files(root):
                archive.write(path, path.relative_to(root).as_posix())
            # Reproducibility files copied from the verified snapshot. Short
            # reports keep these as files instead of printing a code appendix.
            for path in (root / "assets").rglob("*"):
                if (
                    path.is_file()
                    and path.suffix.lower() in {".py", ".m", ".csv", ".json"}
                    and path.suffix.lower() not in workspace.EDITABLE | workspace.ASSETS
                    and path.resolve().is_relative_to(root.resolve())
                    and not any(
                        part.startswith(".") for part in path.relative_to(root).parts
                    )
                ):
                    archive.write(path, path.relative_to(root).as_posix())
            if (root / "preview.pdf").is_file():
                archive.write(root / "preview.pdf", "preview.pdf")
        return Response(
            data.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="paper.zip"'},
        )


@router.get("/{task_id}/history")
async def history(task_id: str, name: str) -> list[dict]:
    """列出指定文件的历史内容，可由编辑器载入再保存。"""
    root = _root(task_id)
    versions = []
    for path in (root / ".history").glob("*/version.json"):
        meta = workspace.read_json(path)
        if meta.get("file") == name:
            versions.append(
                {
                    **meta,
                    "content": (path.parent / "source.txt").read_text(encoding="utf-8"),
                }
            )
    return sorted(versions, key=lambda item: item["saved_at"], reverse=True)[:30]


class PaperRevision(BaseModel):
    """A revision targets saved model chapters and never overwrites old sources."""

    sections: list[str] = Field(min_length=1, max_length=64)
    instructions: str = Field(min_length=1, max_length=10000)
    generation_id: str
    input_revision: str
    source_revision: str


@router.post("/{task_id}/generate")
async def generate(
    task_id: str, revise_style: bool = False, revision: PaperRevision | None = None
) -> dict:
    """独立启动论文手，生成新文件供用户切换，不覆盖现有论文。"""
    async with _lock(task_id):
        root = _root(task_id)
        if task_id in _generations or task_id in _compiling:
            raise HTTPException(409, "论文正在写作或编译，请完成或停止后再操作")
        if _meta(root).get("generation", {}).get("status") == "awaiting_review":
            raise HTTPException(409, "请先接受或拒绝当前章节返修提案。")
        if revise_style and revision is not None:
            raise HTTPException(422, "不能同时选择版式修订和指定章节返修")
        mode = _meta(root).get("mode", "full_paper")
        if WorkflowCheckpoint(root.parent).load().get("status") != "completed":
            raise HTTPException(409, "建模完成并验收后才能生成论文")
        inputs = workspace.read_json(root / "input.json")
        if not inputs:
            raise HTTPException(409, "请先同步建模素材")
        if not settings.WRITER_API_KEY or not settings.WRITER_MODEL:
            raise HTTPException(409, "请在主页面的模型连接中配置论文手")
        generation_id = _generation_id(root, inputs["revision"])
        revision_fields = {}
        if revise_style or revision is not None:
            previous = _meta(root).get("generation", {})
            previous_id = str(previous.get("generation_id", ""))
            if (
                previous.get("mode", "full_paper") != mode
                or previous.get("input_revision") != inputs["revision"]
                or not re.fullmatch(r"[0-9a-f]{10}", previous_id)
            ):
                raise HTTPException(409, "缺少同一建模版本的章节草稿，请先生成初稿")
            cached = workspace.read_json(
                root / ".drafts" / previous_id / ".remit" / "paper_sections.json"
            )
            if not cached:
                raise HTTPException(409, "未找到可复用章节，请先生成初稿")
            removed = {
                "firstPage",
                "RepeatQues",
                "analysisQues",
                "modelAssumption",
                "symbol",
            }
            if revision is not None:
                if (
                    revision.generation_id != previous_id
                    or revision.input_revision != inputs["revision"]
                    or revision.source_revision != workspace.project_revision(root)
                ):
                    raise HTTPException(
                        409, "文稿、章节或计算证据已更新，请刷新后再返修"
                    )
                if not revision.instructions.strip():
                    raise HTTPException(422, "请填写本次章节返修意见")
                requested = set(revision.sections)
                if (
                    len(requested) != len(revision.sections)
                    or not requested <= cached.keys()
                    or any(
                        not re.fullmatch(
                            r"eda|ques[1-9]\d*|sensitivity_analysis|firstPage|RepeatQues|analysisQues|modelAssumption|symbol|judge",
                            key,
                        )
                        for key in requested
                    )
                ):
                    raise HTTPException(422, "只能返修已有章节，且章节不能重复")
                removed = requested.copy()
                scientific = (
                    workspace.read_json(
                        root / ".inputs" / inputs["revision"] / "evidence.json"
                    ).get("solution_results")
                    or {}
                ).keys()
                if requested & scientific:
                    # Summary/front matter derives from the scientific chapters.
                    removed.update(key for key in cached if key not in scientific)
                revision_fields = {
                    "base_generation_id": previous_id,
                    "revised_sections": sorted(removed & cached.keys()),
                }
            from app.services.paper_proposals import evidence_context

            binding, _ = evidence_context(root)
            name = _meta(root)["main"]
            review_base = {
                "name": name,
                "original": workspace.resolve_source(root, name).read_text(
                    encoding="utf-8"
                ),
                "source_revision": workspace.project_revision(root),
                "evidence_version": binding,
                "base_generation": previous,
            }
            revision_fields = {
                "base_generation_id": previous_id,
                "revised_sections": sorted(removed & cached.keys()),
            }
            generation_id = uuid4().hex[:10]
            previous_sections = {key: cached[key] for key in removed if key in cached}
            # Explicit style revision reuses verified scientific chapters. All
            # retained chapters still pass current validation before publication.
            for key in removed:
                cached.pop(key, None)
            workspace.write_json(
                root / ".drafts" / generation_id / ".remit" / "paper_sections.json",
                cached,
            )
            workspace.write_json(
                root / ".drafts" / generation_id / "revision.json",
                {
                    **(
                        revision.model_dump()
                        if revision
                        else {"instructions": "依据现有证据修订首页与前置章节版式。"}
                    ),
                    **revision_fields,
                    "previous_sections": previous_sections,
                    "review_base": review_base,
                },
            )
        _set_generation(
            root,
            "running",
            section="准备写作素材",
            generation_id=generation_id,
            input_revision=inputs["revision"],
            mode=mode,
            **revision_fields,
        )
        _generations[task_id] = asyncio.create_task(
            _generate(task_id, root, inputs["revision"], generation_id)
        )
        return {"status": "running", "generation_id": generation_id, **revision_fields}


@router.post("/{task_id}/cancel")
async def cancel(task_id: str) -> dict:
    """停止当前论文写作与编译，保留建模结果、源码和已有 PDF。"""
    async with _lock(task_id):
        root = _root(task_id)
        task = _generations.get(task_id)
        signal = _compile_cancel.get(task_id)
        if signal is not None:
            signal.set()
            previous = workspace.read_json(root / "compile.json")
            workspace.write_json(
                root / "compile.json", {**previous, "status": "stopping"}
            )
        if task is not None and not task.done():
            _set_generation(
                root, "stopping", message="正在停止，等待当前操作清理完成。"
            )
            if not task.cancelling():
                task.cancel()
        active = signal is not None or (task is not None and not task.done())
        return {"status": "stopping" if active else "idle"}


def _generation_id(root: Path, revision: str) -> str:
    previous = _meta(root).get("generation", {})
    identifier = str(previous.get("generation_id", ""))
    if (
        previous.get("status") in {"failed", "cancelled", "interrupted"}
        and previous.get("input_revision") == revision
        and previous.get("mode", "full_paper") == _meta(root).get("mode", "full_paper")
        and previous.get(
            "plan_revision",
            workspace.digest("{}")
            if not (root / "chapter-plan.json").exists()
            else None,
        )
        == workspace.digest(
            json.dumps(
                workspace.read_json(root / "chapter-plan.json"),
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        and re.fullmatch(r"[0-9a-f]{10}", identifier)
    ):
        return identifier
    return uuid4().hex[:10]


async def _generate(
    task_id: str, root: Path, revision: str, generation_id: str | None = None
) -> None:
    from app.core.agents.writer_agent import WriterAgent
    from app.core.deliverable_contract import (
        validate_writer_section,
        validate_revision_numbers,
        DeliverableValidationError,
    )
    from app.schemas.A2A import WriterResponse
    from app.core.flows import Flows
    from app.core.citations import build_citation_brief
    from app.core.llm.llm_factory import LLMFactory
    from app.models.user_output import UserOutput
    from app.schemas.enums import CompTemplate
    from app.utils.common_utils import get_config_template
    from app.utils.paper_polish import _convert_markdown_to_latex, polish_markdown

    from app.services.message_scope import message_sink
    from app.services.paper_plan import section_context

    snapshot = root / ".inputs" / revision
    generation_id = generation_id or _generation_id(root, revision)
    call_run_id = uuid4().hex
    scratch = root / ".drafts" / generation_id
    original_revision = workspace.project_revision(root)
    mode = _meta(root).get("mode", "full_paper")

    async def record_event(_task_id, event):
        if event.msg_type != "activity":
            with (scratch / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")

    scope = message_sink.set(record_event)
    try:
        evidence = workspace.read_json(snapshot / "evidence.json")
        revision_request = workspace.read_json(scratch / "revision.json")
        plan = workspace.read_json(root / "chapter-plan.json")
        notes = (
            plan.get("notes", "") if plan.get("evidence_revision") == revision else ""
        )
        scratch.mkdir(parents=True, exist_ok=True)
        _set_generation(
            root,
            "running",
            generation_id=generation_id,
            input_revision=revision,
            mode=mode,
            plan_revision=workspace.digest(
                json.dumps(
                    workspace.read_json(root / "chapter-plan.json"),
                    sort_keys=True,
                    ensure_ascii=False,
                )
            ),
        )
        cached = workspace.read_json(scratch / ".remit" / "paper_sections.json")
        # A technical validator fix may make a previously rejected response valid.
        # Every candidate still passes the same current checks before publication.
        for attempt_path in (scratch / ".attempts").glob("*.json"):
            if attempt_path.stem not in cached:
                cached[attempt_path.stem] = workspace.read_json(attempt_path).get(
                    "response", {}
                )
        problem = evidence.get("problem") or {}
        template = CompTemplate(problem.get("comp_template", "CHINA"))
        config = get_config_template(template) or get_config_template(
            CompTemplate.CHINA
        )
        if mode == "short_report":
            config = short_config(config)
        output = UserOutput(str(scratch), int(evidence.get("ques_count") or 0))
        if mode == "short_report":
            output.seq = [
                key
                for key in output.seq
                if key
                not in {"RepeatQues", "analysisQues", "modelAssumption", "symbol"}
            ]
        llm = LLMFactory(task_id).get_writer_llm()
        flows = Flows(
            evidence.get("questions") or {},
            problem.get("user_requirements", ""),
            build_citation_brief(evidence.get("citation_ledger") or {}),
        )
        sections = evidence.get("solution_results") or {}
        missing = [
            key for key in output.seq if key.startswith("ques") and key not in sections
        ]
        if not sections or missing:
            raise DeliverableValidationError(
                "缺少已验证的求解章节：" + ", ".join(missing or ["建模结果"])
            )
        published_name = f"draft-{generation_id}.tex"
        if (root / published_name).exists():
            published_name = f"draft-{generation_id}-{uuid4().hex[:6]}.tex"
        published_text = None
        follow_draft = _meta(root).get("generation", {}).get("follow_draft", True)

        async def publish_draft(*, partial):
            nonlocal original_revision, published_name, published_text, follow_draft
            from app.services.competitions import adapt_generated_source

            if partial and revision_request:
                # A chapter revision keeps the last complete document visible.
                # Checkpoints are already saved; assemble/compile once it is complete.
                return None
            # The assembler also serves complete papers; use only completed
            # sections here so an unfinished chapter never becomes placeholder prose.
            order = output.seq
            try:
                output.seq = [key for key in order if key in output.res]
                markdown = polish_markdown(
                    output.get_result_to_save(), snapshot / "assets", mode=mode
                )
            finally:
                output.seq = order
            asset_prefix = f"assets/{revision}"
            overrides = workspace.figure_overrides(root, revision)
            for asset in sorted(
                (snapshot / "assets").rglob("*"),
                key=lambda item: len(str(item)),
                reverse=True,
            ):
                if asset.is_file():
                    name = asset.relative_to(snapshot / "assets").as_posix()
                    path = overrides.get(name, f"{asset_prefix}/{name}")
                    markdown = markdown.replace(f"]({name})", f"]({path})")
            candidate = scratch / "preview.tex"
            from app.services.call_ledger import scope as call_scope

            with call_scope(task_id, run_id=call_run_id, stage_id="paper:assemble"):
                await run_cancellable(
                    bind(_convert_markdown_to_latex, mode=mode),
                    markdown,
                    candidate,
                    root,
                    scratch,
                    template,
                )
            text = adapt_generated_source(
                root.parent, candidate.read_text(encoding="utf-8")
            )
            text = f"% Remit document mode: {mode}\n" + text
            if revision_request:
                from app.services.paper_proposals import create_proposal

                base = revision_request.get("review_base")
                if not base:
                    raise ValueError(
                        "旧返修任务缺少审阅基准，请重新提交章节返修；原稿已保留。"
                    )
                async with _lock(task_id):
                    proposal = create_proposal(
                        root,
                        base["name"],
                        base["original"],
                        text,
                        "章节返修：" + str(revision_request.get("instructions", "")),
                        base["evidence_version"],
                        chapter_revision={
                            "generation_id": generation_id,
                            "source_revision": base["source_revision"],
                            "base_generation": base["base_generation"],
                        },
                    )
                    _set_generation(
                        root,
                        "awaiting_review",
                        proposal_id=proposal["id"],
                        partial=False,
                        completed_sections=list(output.res),
                        message="返修提案已生成，请检查差异；接受后才写入并编译。",
                    )
                return {"status": "awaiting_review", "proposal_id": proposal["id"]}
            async with _lock(task_id):
                follow_draft = (
                    follow_draft
                    and workspace.project_revision(root) == original_revision
                )
                target = root / published_name
                if (
                    target.exists()
                    and target.read_text(encoding="utf-8") != published_text
                ):
                    # A user edited this generated file; retain it and publish separately.
                    published_name = f"draft-{generation_id}-{uuid4().hex[:6]}.tex"
                    target = root / published_name
                shutil.copytree(
                    snapshot / "assets", root / asset_prefix, dirs_exist_ok=True
                )
                target.write_text(text, encoding="utf-8")
                published_text = text
                meta = _meta(root)
                meta.setdefault("document_modes", {})[published_name] = mode
                if follow_draft:
                    meta["main"] = published_name
                workspace.write_json(root / "workspace.json", meta)
                _set_generation(
                    root,
                    "running",
                    file=published_name,
                    partial=partial,
                    follow_draft=follow_draft,
                    completed_sections=list(output.res),
                    input_revision=revision,
                    message=(
                        "已更新部分草稿，后续章节仍在撰写。"
                        if partial
                        else "章节已齐，正在检查 PDF 排版。"
                    )
                    if follow_draft
                    else "检测到手工编辑，草稿已另存，原文件保持不变。",
                )
                original_revision = workspace.project_revision(root)
            if follow_draft:
                try:
                    return await compile_source(task_id)
                except Exception as exc:
                    return {"status": "failed", "log": str(exc)}
            return None

        def check_revision(key, content):
            previous = (
                revision_request.get("previous_sections", {})
                .get(key, {})
                .get("response_content")
            )
            if previous:
                entries = evidence.get("solution_results") or {}
                relevant = [entries[key]] if key in entries else entries.values()
                validate_revision_numbers(
                    previous,
                    content,
                    grounding_values={
                        value
                        for entry in relevant
                        for value in entry.get("grounding_values", [])
                    },
                )

        async def write_validated(agent, key, prompt, *, images=None, validation=None):
            validation = validation or {}
            if key in revision_request.get("revised_sections", []):
                prompt += (
                    "\n【本次章节返修】保持计算证据与其适用边界，依据以下意见修正本章。"
                    "逐项保留指标名称、数值、单位及适用范围，不合并指标或遗漏数值。若修改需要新实验，明确说明缺口，不得补造结果。\n"
                    + str(revision_request.get("instructions", ""))
                )
                previous_section = revision_request.get("previous_sections", {}).get(
                    key, {}
                )
                if previous_section.get("response_content"):
                    prompt += (
                        "\n【本章旧稿，仅作修订对象；不能覆盖真实证据】\n"
                        + previous_section["response_content"]
                    )
            for attempt in range(2):
                from app.services.call_ledger import scope as call_scope

                with call_scope(
                    task_id,
                    run_id=call_run_id,
                    stage_id=f"write:{key}",
                    purpose="paper_revision"
                    if attempt or revision_request
                    else "normal_work",
                ):
                    from app.services.work_timing import ameasure

                    async with ameasure(task_id, "writing"):
                        response = await agent.run(
                            prompt, available_images=images, sub_title=key
                        )
                # Keep rejected prose for diagnosis, never publish it as a passed section.
                workspace.write_json(
                    scratch / ".attempts" / f"{key}.json",
                    {"attempt": attempt + 1, "response": response.model_dump()},
                )
                try:
                    check_revision(key, response.response_content)
                    validate_writer_section(
                        key,
                        response.response_content,
                        omitted_images=response.omitted_images,
                        mode=mode,
                        **validation,
                    )
                except DeliverableValidationError as exc:
                    if attempt:
                        raise
                    async with _lock(task_id):
                        _set_generation(
                            root,
                            "running",
                            section=key,
                            message="章节校验发现缺项，墨墨正在修订（1/1）",
                        )
                    prompt = (
                        "请修订刚才的完整章节，校验反馈如下：\n"
                        + str(exc)
                        + "\n请逐项对照原始证据核对所有数值及分类口径，保留有依据的内容与图表。"
                        "不要编造数据，不要以聊天答复代替正文，只返回修订后的完整章节。"
                    )
                else:
                    return response
            raise RuntimeError("章节修订未返回结果")

        core_changed = False
        for key in output.seq:
            if key not in sections:
                continue
            entry = sections[key]
            validation = {
                "required_images": entry.get("paper_ready_images", []),
                "quality_report": entry.get("quality_report"),
                "question_text": entry.get("question_text", ""),
                "grounding_values": entry.get("grounding_values", []),
            }
            if key in cached:
                try:
                    saved = WriterResponse.model_validate(cached[key])
                    check_revision(key, saved.response_content)
                    validate_writer_section(
                        key,
                        saved.response_content,
                        omitted_images=saved.omitted_images,
                        mode=mode,
                        **validation,
                    )
                except (ValueError, DeliverableValidationError):
                    pass
                else:
                    output.set_res(key, saved)
                    continue
            core_changed = True
            async with _lock(task_id):
                _set_generation(root, "running", section=key, input_revision=revision)
            agent = WriterAgent(
                task_id,
                llm,
                comp_template=template,
                context_window=settings.WRITER_CONTEXT_WINDOW,
                mode=mode,
            )
            prompt = entry.get("writer_prompt") or (
                f"根据已验证的建模成果撰写 {key}，不得编造结果。题目：{problem.get('ques_all', '')}\n"
                + json.dumps(entry, ensure_ascii=False)
                + "\n"
                + str(config.get(key, ""))
            )
            if mode == "short_report":
                prompt = (
                    f"根据以下已验证证据撰写短报告的 {key} 章节。题目：{problem.get('ques_all', '')}\n"
                    + json.dumps(
                        {k: v for k, v in entry.items() if k != "writer_prompt"},
                        ensure_ascii=False,
                    )
                )
            prompt += (
                flows._citation_block()
                + "\n"
                + str(evidence.get("evidence_notice") or "")
            )
            from app.services.writer_evidence import source_excerpt

            prompt += source_excerpt(
                snapshot, entry, evidence.get("artifact_hashes") or {}
            )
            prompt += section_context(key, evidence, notes)
            response = await write_validated(
                agent,
                key,
                prompt,
                images=entry.get("paper_ready_images", []),
                validation=validation,
            )
            output.set_res(key, response)
            output.save_result()
            await publish_draft(partial=True)
        for key, prompt in flows.get_write_flows(
            output, config, problem.get("ques_all", "")
        ).items():
            if key not in output.seq:
                continue
            prompt += "\n" + str(evidence.get("evidence_notice") or "")
            prompt += section_context(key, evidence, notes)
            if not core_changed and key in cached:
                try:
                    saved = WriterResponse.model_validate(cached[key])
                    check_revision(key, saved.response_content)
                    validate_writer_section(key, saved.response_content, mode=mode)
                except (ValueError, DeliverableValidationError):
                    pass
                else:
                    output.set_res(key, saved)
                    continue
            async with _lock(task_id):
                _set_generation(root, "running", section=key, input_revision=revision)
            agent = WriterAgent(
                task_id,
                llm,
                comp_template=template,
                context_window=settings.WRITER_CONTEXT_WINDOW,
                mode=mode,
            )
            response = await write_validated(agent, key, prompt)
            output.set_res(key, response)
            output.save_result()
            await publish_draft(partial=True)
        # Responses recovered from rejected attempts are now validated too.
        # Persist them so later selective revisions can find every chapter.
        output.save_result()
        compiled = await publish_draft(partial=False)
        if compiled and compiled.get("status") == "awaiting_review":
            return
        review = (compiled or {}).get("layout_review", {})
        abstract_issues = [
            item
            for item in review.get("blocking_issues", [])
            if item.startswith("摘要")
        ]
        if abstract_issues and "firstPage" in output.res:
            _set_generation(
                root,
                "running",
                section="firstPage",
                message="首页版式检查未通过，墨墨正在按实际 PDF 修订摘要（1/1）",
            )
            agent = WriterAgent(
                task_id,
                llm,
                comp_template=template,
                context_window=settings.WRITER_CONTEXT_WINDOW,
                mode=mode,
            )
            prompt = flows.get_write_flows(output, config, problem.get("ques_all", ""))[
                "firstPage"
            ]
            prompt += "\n实际 PDF 检查反馈：" + "；".join(abstract_issues)
            prompt += "\n原摘要：\n" + output.res["firstPage"]["response_content"]
            response = await write_validated(agent, "firstPage", prompt)
            output.set_res("firstPage", response)
            output.save_result()
            compiled = await publish_draft(partial=False)
            review = (compiled or {}).get("layout_review", {})
        if compiled and (
            compiled.get("status") != "completed" or review.get("blocking_issues")
        ):
            _set_generation(
                root,
                "failed",
                error="草稿已保留，排版仍需修订："
                + "；".join(
                    review.get("issues")
                    or [str(compiled.get("log", "PDF 编译失败"))[-1200:]]
                ),
            )
        else:
            _set_generation(
                root,
                "completed",
                partial=False,
                message="初稿已生成并通过自动排版检查，请核对正文、图表与证据。"
                if compiled
                else "初稿已另存，原编辑文件保持不变；请打开草稿并编译核验。",
            )
    except asyncio.CancelledError:
        async with _lock(task_id):
            _set_generation(
                root, "cancelled", message="已停止，章节草稿保留在项目内部目录"
            )
    except Exception as exc:
        async with _lock(task_id):
            _set_generation(root, "failed", error=str(exc)[:3000])
    finally:
        message_sink.reset(scope)
        _generations.pop(task_id, None)


@router.get("/{task_id}/chapter-plan")
async def get_chapter_plan(task_id: str):
    """显示当前证据生成的章节计划，提供修改冲突标识。"""
    async with _lock(task_id):
        root = _root(task_id)
        plan = workspace.read_json(root / "chapter-plan.json")
        text = json.dumps(plan, sort_keys=True, ensure_ascii=False)
        return {**plan, "version": workspace.digest(text)}


class ChapterPlanNotes(BaseModel):
    """只允许修改组织意见，证据字段由计算结果提供。"""

    notes: str = Field(max_length=10000)
    version: str
    evidence_revision: str


@router.put("/{task_id}/chapter-plan")
async def save_chapter_plan(task_id: str, request: ChapterPlanNotes):
    async with _lock(task_id):
        root = _root(task_id)
        if task_id in _generations:
            raise HTTPException(409, "正在写作，请停止后再修改章节计划。")
        plan = workspace.read_json(root / "chapter-plan.json")
        current_version = workspace.digest(
            json.dumps(plan, sort_keys=True, ensure_ascii=False)
        )
        if (
            current_version != request.version
            or plan.get("evidence_revision") != request.evidence_revision
            or workspace.read_json(root / "input.json").get("revision")
            != request.evidence_revision
        ):
            raise HTTPException(409, "章节计划或证据已变化，请重新读取后修改。")
        plan["notes"] = request.notes
        workspace.write_json(root / "chapter-plan.json", plan)
        return {
            **plan,
            "version": workspace.digest(
                json.dumps(plan, sort_keys=True, ensure_ascii=False)
            ),
        }
