"""论文工作区 API；写作任务与建模任务有独立状态和生命周期。"""

import asyncio
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.config.setting import settings
from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.routers.files_router import _resolve_task_directory
from app.services import writing_workspace as workspace
from app.services.team_state import compiling_tasks
from app.services.async_io import run_blocking

router = APIRouter(prefix="/api/writing", tags=["writing"])
_locks: dict[str, asyncio.Lock] = {}
_generations: dict[str, asyncio.Task] = {}
_compiling = compiling_tasks


async def shutdown_writers() -> None:
    """退出服务前停止论文任务并保存中断状态。"""
    active = list(_generations.values())
    for task in active:
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
        k: previous[k] for k in ("generation_id", "input_revision") if k in previous
    }
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
            meta.get("generation", {}).get("status") == "running"
            and task_id not in _generations
        ):
            _set_generation(
                root, "interrupted", error="服务已重启，上次写作中断。可重新生成。"
            )
            meta = _meta(root)
        compile_result = workspace.read_json(root / "compile.json")
        return {
            **meta,
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
        build, main, revision = await asyncio.to_thread(workspace.prepare_build, root)
        _compiling.add(task_id)
        from app.services.team_state import record

        record(
            root.parent, "writer", "compile", "开始编译 LaTeX", {"status": "running"}
        )
    try:
        result = await run_blocking(workspace.compile_build, build, main, revision)
        async with _lock(task_id):
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
            else:
                result["pdf_revision"] = previous.get("pdf_revision")
                result["page_count"] = previous.get("page_count", 0)
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
    except Exception as exc:
        record(root.parent, "writer", "error", f"编译中断：{str(exc)[:300]}")
        raise
    finally:
        _compiling.discard(task_id)


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
                min(2.0, scale, 2400 / max(current.rect.width, current.rect.height)),
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

            for name, content in export_notes(root.parent).items():
                archive.writestr(name, content)
            for path in workspace.source_files(root):
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


@router.post("/{task_id}/generate")
async def generate(task_id: str) -> dict:
    """独立启动论文手，生成新文件供用户切换，不覆盖现有论文。"""
    async with _lock(task_id):
        root = _root(task_id)
        if task_id in _generations:
            raise HTTPException(409, "论文手正在生成")
        if WorkflowCheckpoint(root.parent).load().get("status") != "completed":
            raise HTTPException(409, "建模完成并验收后才能生成论文")
        inputs = workspace.read_json(root / "input.json")
        if not inputs:
            raise HTTPException(409, "请先同步建模素材")
        if not settings.WRITER_API_KEY or not settings.WRITER_MODEL:
            raise HTTPException(409, "请在主页面的模型连接中配置论文手")
        generation_id = _generation_id(root, inputs["revision"])
        _set_generation(
            root,
            "running",
            section="准备写作素材",
            generation_id=generation_id,
            input_revision=inputs["revision"],
        )
        _generations[task_id] = asyncio.create_task(
            _generate(task_id, root, inputs["revision"], generation_id)
        )
        return {"status": "running"}


@router.post("/{task_id}/cancel")
async def cancel(task_id: str) -> dict:
    """只停止论文手，不影响建模结果与手工源码。"""
    task = _generations.get(task_id)
    if task:
        task.cancel()
    return {"status": "stopping" if task else "idle"}


def _generation_id(root: Path, revision: str) -> str:
    previous = _meta(root).get("generation", {})
    identifier = str(previous.get("generation_id", ""))
    if (
        previous.get("status") in {"failed", "cancelled", "interrupted"}
        and previous.get("input_revision") == revision
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

    snapshot = root / ".inputs" / revision
    generation_id = generation_id or _generation_id(root, revision)
    scratch = root / ".drafts" / generation_id

    async def record_event(_task_id, event):
        if event.msg_type != "activity":
            with (scratch / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")

    scope = message_sink.set(record_event)
    try:
        evidence = workspace.read_json(snapshot / "evidence.json")
        scratch.mkdir(parents=True, exist_ok=True)
        _set_generation(
            root, "running", generation_id=generation_id, input_revision=revision
        )
        cached = workspace.read_json(scratch / ".remit" / "paper_sections.json")
        problem = evidence.get("problem") or {}
        template = CompTemplate(problem.get("comp_template", "CHINA"))
        config = get_config_template(template) or get_config_template(
            CompTemplate.CHINA
        )
        output = UserOutput(str(scratch), int(evidence.get("ques_count") or 0))
        llm = LLMFactory(task_id).get_writer_llm()
        flows = Flows(
            evidence.get("questions") or {},
            problem.get("user_requirements", ""),
            build_citation_brief(evidence.get("citation_ledger") or {}),
        )
        sections = evidence.get("solution_results") or {}
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
                    validate_writer_section(key, saved.response_content, **validation)
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
            )
            prompt = entry.get("writer_prompt") or (
                f"根据已验证的建模成果撰写 {key}，不得编造结果。题目：{problem.get('ques_all', '')}\n"
                + json.dumps(entry, ensure_ascii=False)
                + "\n"
                + str(config.get(key, ""))
            )
            prompt += flows._citation_block() + "\n" + str(evidence.get("evidence_notice") or "")
            response = await agent.run(
                prompt,
                available_images=entry.get("paper_ready_images", []),
                sub_title=key,
            )
            validate_writer_section(
                key,
                response.response_content,
                **validation,
            )
            output.set_res(key, response)
            output.save_result()
        for key, prompt in flows.get_write_flows(
            output, config, problem.get("ques_all", "")
        ).items():
            prompt += "\n" + str(evidence.get("evidence_notice") or "")
            if not core_changed and key in cached:
                try:
                    saved = WriterResponse.model_validate(cached[key])
                    validate_writer_section(key, saved.response_content)
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
            )
            response = await agent.run(prompt, sub_title=key)
            validate_writer_section(key, response.response_content)
            output.set_res(key, response)
            output.save_result()
        markdown = polish_markdown(output.get_result_to_save(), snapshot / "assets")
        asset_prefix = f"assets/{revision}"
        for asset in sorted(
            (snapshot / "assets").rglob("*"),
            key=lambda item: len(str(item)),
            reverse=True,
        ):
            if asset.is_file():
                name = asset.relative_to(snapshot / "assets").as_posix()
                markdown = markdown.replace(f"]({name})", f"]({asset_prefix}/{name})")
        name = f"draft-{generation_id}.tex"
        await asyncio.to_thread(
            _convert_markdown_to_latex,
            markdown,
            scratch / name,
            root,
            scratch,
            template,
        )
        from app.services.competitions import adapt_generated_source

        draft_path = scratch / name
        draft_path.write_text(
            adapt_generated_source(root.parent, draft_path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        async with _lock(task_id):
            shutil.copytree(
                snapshot / "assets", root / asset_prefix, dirs_exist_ok=True
            )
            shutil.copy2(scratch / name, root / name)
            _set_generation(
                root,
                "completed",
                file=name,
                input_revision=revision,
                message="初稿已生成，选择此文件并设为主文件后编译；请核对正文与证据。",
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
