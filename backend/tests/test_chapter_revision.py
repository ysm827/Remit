"""Selective revision must preserve old work, reject conflicts and resume locally."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.setting import settings
from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.routers import writing_router as router
from app.schemas.A2A import WriterResponse
from app.schemas.request import Problem
from app.services import writing_workspace as ws

BODY = """## 模型与验证
使用带截距线性模型 $y=ax+b$，其中 $a$ 为斜率，$b$ 为截距。
计算读取 observed.csv 的六行合成观测，metrics.json 中斜率为 2、截距为 1。
独立复算采用中心化求和公式，按同一口径核对系数及逐点拟合值。
这些数据只用于数值核验，没有独立测试集，也没有观测噪声实验。
不能据训练拟合结果推断现实数据的预测能力，后续应用需要重新收集数据并评估误差。
"""
FRONT = """# 数值核验短报告
## 摘要
本报告使用 **带截距线性回归** 核对给定合成观测，斜率为 **2**。
主实现和独立复算按统一口径比对，原始输入未被修改。该结论仅描述给定数据上的计算一致性；
没有独立测试集、噪声实验或现实测量依据，不能推断未知样本上的预测能力。
**关键词：数值核验；独立复算**
"""


@pytest.fixture
def revision_case(tmp_path, monkeypatch):
    checkpoint = WorkflowCheckpoint(tmp_path)
    state = checkpoint.initialize(Problem(task_id="revision-case"))
    state.update(
        status="completed",
        ques_count=1,
        questions={"ques1": "核对六行计算"},
        solution_results={"ques1": {"writer_prompt": "verify", "artifacts": []}},
    )
    checkpoint.save(state)
    root = ws.ensure_workspace(tmp_path)
    inputs = ws.sync_results(tmp_path, state)
    cached = {
        key: WriterResponse(response_content=text).model_dump()
        for key, text in {
            "ques1": BODY,
            "firstPage": FRONT,
            "judge": "## 结论\n" + BODY,
        }.items()
    }
    ws.write_json(root / ".drafts/0123456789/.remit/paper_sections.json", cached)
    meta = ws.read_json(root / "workspace.json")
    meta.update(
        mode="short_report",
        generation={
            "status": "completed",
            "generation_id": "0123456789",
            "input_revision": inputs["revision"],
            "mode": "short_report",
            "completed_sections": list(cached),
        },
    )
    ws.write_json(root / "workspace.json", meta)
    monkeypatch.setattr(router, "_resolve_task_directory", lambda _: tmp_path)
    monkeypatch.setattr(settings, "WRITER_API_KEY", "test-only")
    monkeypatch.setattr(settings, "WRITER_MODEL", "test-model")
    router._locks.clear()
    router._generations.clear()
    router._compiling.clear()
    app = FastAPI()
    app.include_router(router.router)
    request = {
        "sections": ["judge"],
        "instructions": "将最大系数差改为最大斜率差，保留适用边界。",
        "generation_id": "0123456789",
        "input_revision": inputs["revision"],
        "source_revision": ws.project_revision(root),
    }
    with TestClient(app) as client:
        yield client, root, cached, request
    router._generations.clear()
    router._locks.clear()


@pytest.mark.parametrize(
    "target,rewritten",
    [("judge", {"judge"}), ("ques1", {"ques1", "firstPage", "judge"})],
)
def test_target_scope_preserves_unaffected_cache_and_source(
    revision_case, target, rewritten
):
    client, root, cached, request = revision_case
    before = (root / "main.tex").read_bytes()
    with patch.object(router, "_generate", new=AsyncMock()):
        response = client.post(
            "/api/writing/revision-case/generate",
            json={**request, "sections": [target]},
        )
    assert response.status_code == 200
    result = response.json()
    assert set(result["revised_sections"]) == rewritten
    scratch = root / ".drafts" / result["generation_id"]
    assert ws.read_json(scratch / ".remit/paper_sections.json") == {
        k: v for k, v in cached.items() if k not in rewritten
    }
    assert ws.read_json(scratch / "revision.json")["previous_sections"] == {
        k: v for k, v in cached.items() if k in rewritten
    }
    assert (
        ws.read_json(root / ".drafts/0123456789/.remit/paper_sections.json") == cached
    )
    assert (root / "main.tex").read_bytes() == before


@pytest.mark.parametrize(
    "field", ["generation_id", "input_revision", "source_revision"]
)
def test_revision_rejects_stale_version_before_model_calls(revision_case, field):
    client, root, _, request = revision_case
    with patch.object(router, "_generate", new=AsyncMock()) as start:
        response = client.post(
            "/api/writing/revision-case/generate", json={**request, field: "stale"}
        )
    assert response.status_code == 409
    start.assert_not_called()
    assert len(list((root / ".drafts").iterdir())) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"sections": ["missing"]},
        {"sections": ["judge", "judge"]},
        {"instructions": "  "},
    ],
)
def test_invalid_revision_is_not_started(revision_case, change):
    client, _, _, request = revision_case
    with patch.object(router, "_generate", new=AsyncMock()) as start:
        response = client.post(
            "/api/writing/revision-case/generate", json={**request, **change}
        )
    assert response.status_code == 422
    start.assert_not_called()


def test_failure_resume_only_rewrites_target_and_compiles_complete_draft(revision_case):
    client, root, cached, request = revision_case
    with patch.object(router, "_generate", new=AsyncMock()):
        result = client.post("/api/writing/revision-case/generate", json=request).json()
    router._generations.clear()
    before = (root / "main.tex").read_bytes()
    checkpoint = (root.parent / "workflow_state.json").read_bytes()
    writer = AsyncMock(
        side_effect=[
            RuntimeError("interrupted"),
            WriterResponse(
                response_content="## 结论与局限\n"
                + BODY
                + "最大斜率差与截距差分别记录。"
            ),
        ]
    )
    compile_mock = AsyncMock(
        return_value={"status": "completed", "layout_review": {"blocking_issues": []}}
    )

    def convert(markdown, path, *_, **__):
        path.write_text(markdown, encoding="utf-8")

    with (
        patch(
            "app.core.llm.llm_factory.LLMFactory.get_writer_llm", return_value=object()
        ),
        patch("app.core.agents.writer_agent.WriterAgent.run", writer),
        patch("app.utils.paper_polish._convert_markdown_to_latex", side_effect=convert),
        patch(
            "app.services.competitions.adapt_generated_source",
            side_effect=lambda _, text: text,
        ),
        patch.object(router, "compile_source", compile_mock),
    ):
        asyncio.run(
            router._generate(
                "revision-case",
                root,
                request["input_revision"],
                result["generation_id"],
            )
        )
        assert ws.read_json(root / "workspace.json")["generation"]["status"] == "failed"
        assert (root / "main.tex").read_bytes() == before
        compile_mock.assert_not_awaited()
        assert (
            router._generation_id(root, request["input_revision"])
            == result["generation_id"]
        )
        asyncio.run(
            router._generate(
                "revision-case",
                root,
                request["input_revision"],
                result["generation_id"],
            )
        )
    assert [call.kwargs["sub_title"] for call in writer.await_args_list] == [
        "judge",
        "judge",
    ]
    assert request["instructions"] in writer.await_args.args[0]
    assert cached["judge"]["response_content"] in writer.await_args.args[0]
    compile_mock.assert_not_awaited()
    generation = ws.read_json(root / "workspace.json")["generation"]
    assert generation["status"] == "awaiting_review"
    proposal = ws.read_json(root / ".proposals" / (generation["proposal_id"] + ".json"))
    assert proposal["status"] == "pending"
    assert proposal["version"] == ws.digest(
        (root / "main.tex").read_text(encoding="utf-8")
    )
    assert "最大斜率差" in proposal["diff"]
    final = ws.read_json(
        root / ".drafts" / result["generation_id"] / ".remit/paper_sections.json"
    )
    assert (
        final["ques1"] == cached["ques1"] and final["firstPage"] == cached["firstPage"]
    )
    assert final["judge"] != cached["judge"]
    assert (root.parent / "workflow_state.json").read_bytes() == checkpoint
    assert (root / "main.tex").read_bytes() == before


def test_revision_cancel_endpoint_stops_actual_pandoc(revision_case, blocked_pandoc):
    client, root, cached, request = revision_case
    marker, processes = blocked_pandoc
    with patch.object(router, "_generate", new=AsyncMock()):
        result = client.post("/api/writing/revision-case/generate", json=request).json()
    router._generations.clear()
    previous = (root / "main.tex").read_bytes()
    (root / "preview.pdf").write_bytes(b"previous verified PDF")
    compile_mock = AsyncMock()
    app = FastAPI()
    app.include_router(router.router)

    async def exercise():
        job = asyncio.create_task(
            router._generate(
                "revision-case",
                root,
                request["input_revision"],
                result["generation_id"],
            )
        )
        router._generations["revision-case"] = job
        try:
            for _ in range(200):
                if marker.exists() or job.done():
                    break
                await asyncio.sleep(0.02)
            assert marker.exists(), ws.read_json(root / "workspace.json")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as api:
                response = await api.post("/api/writing/revision-case/cancel")
                assert response.status_code == 200
                assert response.json()["status"] == "stopping"
            await asyncio.wait_for(job, 4)
            assert (
                ws.read_json(root / "workspace.json")["generation"]["status"]
                == "cancelled"
            )
            assert all(not process.is_running() for process in processes)
            assert (root / "main.tex").read_bytes() == previous
            assert (root / "preview.pdf").read_bytes() == b"previous verified PDF"
            compile_mock.assert_not_awaited()
            assert "revision-case" not in router._generations
        finally:
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)

    with (
        patch(
            "app.core.llm.llm_factory.LLMFactory.get_writer_llm", return_value=object()
        ),
        patch(
            "app.core.agents.writer_agent.WriterAgent.run",
            new=AsyncMock(return_value=WriterResponse(**cached["judge"])),
        ),
        patch.object(router, "compile_source", compile_mock),
    ):
        asyncio.run(exercise())


@pytest.mark.parametrize("decision", ["accept", "reject", "edited", "evidence", "main"])
def test_chapter_review_preserves_user_work_and_reuses_only_accepted_cache(
    revision_case, decision
):
    from app.services import paper_proposals as pp
    from fastapi import HTTPException

    client, root, cached, request = revision_case
    with patch.object(router, "_generate", new=AsyncMock()):
        result = client.post("/api/writing/revision-case/generate", json=request).json()
    router._generations.clear()
    original = (root / "main.tex").read_bytes()
    compile_mock = AsyncMock(return_value={"status": "completed"})

    def convert(markdown, path, *_, **__):
        path.write_text(markdown, encoding="utf-8")

    with (
        patch(
            "app.core.llm.llm_factory.LLMFactory.get_writer_llm", return_value=object()
        ),
        patch(
            "app.core.agents.writer_agent.WriterAgent.run",
            new=AsyncMock(
                return_value=WriterResponse(
                    response_content="## 结论\n" + BODY + "修订说明。"
                )
            ),
        ),
        patch("app.utils.paper_polish._convert_markdown_to_latex", side_effect=convert),
        patch(
            "app.services.competitions.adapt_generated_source",
            side_effect=lambda _, text: text,
        ),
        patch.object(router, "compile_source", compile_mock),
    ):
        asyncio.run(
            router._generate(
                "revision-case",
                root,
                request["input_revision"],
                result["generation_id"],
            )
        )
        generation = ws.read_json(root / "workspace.json")["generation"]
        assert generation["status"] == "awaiting_review"
        assert (root / "main.tex").read_bytes() == original
        compile_mock.assert_not_awaited()
        assert client.post("/api/writing/revision-case/generate").status_code == 409
        if decision == "edited":
            (root / "main.tex").write_text("manual user text", encoding="utf-8")
        elif decision == "evidence":
            state = ws.read_json(root.parent / "workflow_state.json")
            state["questions"]["ques1"] = "changed question"
            ws.write_json(root.parent / "workflow_state.json", state)
        elif decision == "main":
            meta = ws.read_json(root / "workspace.json")
            meta["main"] = "other.tex"
            (root / "other.tex").write_text("other document", encoding="utf-8")
            ws.write_json(root / "workspace.json", meta)
        before_decision = (root / "main.tex").read_bytes()
        if decision in {"edited", "evidence", "main"}:
            with pytest.raises(HTTPException) as error:
                asyncio.run(
                    pp.decide(
                        "revision-case",
                        generation["proposal_id"],
                        pp.Decision(accept=True),
                    )
                )
            assert error.value.status_code == 409
            assert (root / "main.tex").read_bytes() == before_decision
            compile_mock.assert_not_awaited()
            decision = "reject"
        asyncio.run(
            pp.decide(
                "revision-case",
                generation["proposal_id"],
                pp.Decision(accept=decision == "accept"),
            )
        )
        after = ws.read_json(root / "workspace.json")["generation"]
        if decision == "accept":
            compile_mock.assert_awaited_once()
            assert after["generation_id"] == result["generation_id"]
            assert (root / "main.tex").read_bytes() != original
            assert list((root / ".history").glob("*/source.txt"))
        else:
            compile_mock.assert_not_awaited()
            assert after["generation_id"] == request["generation_id"]
            assert (root / "main.tex").read_bytes() == before_decision
        assert (
            ws.read_json(root / ".drafts/0123456789/.remit/paper_sections.json")
            == cached
        )


def test_real_revision_numeric_regression_and_equivalent_notation():
    from app.core.deliverable_contract import (
        validate_revision_numbers,
        DeliverableValidationError,
    )

    original = "最大斜率差 8.881784197001252e-16，最大截距差 2.9976021664879227e-15"
    failed = "最大系数差 8.881784197001252e-16"
    with pytest.raises(DeliverableValidationError, match="2.9976021664879227"):
        validate_revision_numbers(original, failed)
    validate_revision_numbers("误差 0.001，样本 6", r"误差 1 \times 10^{-3}，样本 6.0")


def test_revision_can_restore_evidence_precision_without_loosening_tolerance():
    from app.core.deliverable_contract import (
        DeliverableValidationError,
        validate_revision_numbers,
    )

    exact = 9.532069271420559e-31
    validate_revision_numbers(
        "MSE 9.53e-31；再次展示 9.532e-31",
        f"MSE {exact}",
        grounding_values={exact},
    )
    for original, revised, evidence in [
        ("9.53e-31", str(exact), set()),
        ("9.53e-31", "9.54e-31", {9.54e-31}),
        (str(exact), "9.53e-31", {exact, 9.53e-31}),
        (str(exact), "0", {exact, 0}),
        ("0", str(exact), {exact}),
        ("6", "6.1", {6.1}),
        ("9.53e-31", "-9.532069271420559e-31", {-exact}),
        (
            "斜率差 4.44e-16，截距差 1.78e-15",
            "4.440892098500626e-16",
            {4.440892098500626e-16},
        ),
    ]:
        with pytest.raises(DeliverableValidationError):
            validate_revision_numbers(original, revised, grounding_values=evidence)
