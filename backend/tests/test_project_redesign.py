"""准备阶段、关键验收、源码审阅和赛事配置的真实写入边界。"""

import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from app.core.workflow import RemitWorkFlow, WorkflowApprovalRequired
from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.routers import project_router, team_router, modeling_router, writing_router
from app.services import competitions, paper_proposals, writing_workspace as ws
from app.services import team_state as team
from app.schemas.request import Problem


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["truncated", "invalid", "schema"])
async def test_prepare_retries_incomplete_plan_once_without_starting(
    draft, monkeypatch, failure
):
    plan = {
        "kind": "plan",
        "title": "运输优化",
        "understanding": "检查运输数据",
        "steps": ["计算安全载荷"],
        "questions": ["请提供缺失的载荷参数"],
    }
    bad = SimpleNamespace(content=json.dumps(plan), finish_reason="max_output_tokens")
    if failure == "invalid":
        bad = SimpleNamespace(content='{"kind":"plan","title":"未结束')
    elif failure == "schema":
        bad = SimpleNamespace(content='{"kind":"plan","steps":[]}')
    llm = SimpleNamespace(
        chat=AsyncMock(side_effect=[bad, SimpleNamespace(content=json.dumps(plan))])
    )
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    await project_router.prepare(draft, "确认")
    assert llm.chat.await_count == 2
    assert project_router.metadata(draft)["preflight"]["questions"] == plan["questions"]
    assert project_router.metadata(draft)["status"] == "needs_info"
    assert len([e for e in team.events(draft) if e["kind"] == "preflight"]) == 1
    assert not (draft / "workflow_state.json").exists()


@pytest.mark.anyio
async def test_prepare_repeated_bad_json_preserves_old_plan_and_files(
    draft, monkeypatch
):
    meta = project_router.metadata(draft)
    meta.update(status="ready", preflight={"id": "keep", "steps": ["原计划"]})
    ws.write_json(draft / ".project.json", meta)
    original = (draft / ".project.json").read_bytes()
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(content='{"kind":"plan","title":"半截')
        )
    )
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    with pytest.raises(HTTPException) as error:
        await project_router.prepare(draft, "确认")
    assert error.value.status_code == 502
    assert "原有计划和附件已保留" in error.value.detail
    assert llm.chat.await_count == 2
    assert (draft / ".project.json").read_bytes() == original
    assert not any(e["kind"] == "preflight" for e in team.events(draft))
    assert not (draft / "workflow_state.json").exists()


@pytest.mark.anyio
async def test_prepare_transport_error_is_not_retried_as_json(draft, monkeypatch):
    llm = SimpleNamespace(chat=AsyncMock(side_effect=RuntimeError("unauthorized")))
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    with pytest.raises(RuntimeError, match="unauthorized"):
        await project_router.prepare(draft, "确认")
    llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_after_step_adjustment_is_not_visible_until_step_completes(draft):
    cp = WorkflowCheckpoint(draft)
    state = cp.initialize(Problem(task_id=draft.name))
    cp.start_node(state, "modeler")
    body = team_router.ChatRequest(
        request_id="queued-adjustment", content="保存误差图", timing="after_step"
    )
    await team_router.apply_adjustment(draft.name, body, draft, BackgroundTasks())
    assert not team.snapshot(draft)["directives"]
    assert "保存误差图" not in team.context_for(draft.name, "ModelerAgent")
    cp.complete_node(state, "modeler")
    assert "保存误差图" in team.context_for(draft.name, "ModelerAgent")
    team.activate_directives(draft, cp.load())
    assert len(team.snapshot(draft)["directives"]) == 1


@pytest.mark.anyio
async def test_immediate_adjustment_waits_for_stop_before_resuming(draft, monkeypatch):
    cp = WorkflowCheckpoint(draft)
    state = cp.initialize(Problem(task_id=draft.name))
    cp.start_node(state, "coordinator")
    modeling_router._active_tasks[draft.name] = (None, None)

    async def cancel(task_id):
        modeling_router._active_tasks.pop(task_id)
        cp.mark_status("stopped")

    monkeypatch.setattr(modeling_router, "cancel_task", cancel)
    resume = AsyncMock()
    monkeypatch.setattr(modeling_router, "resume_task", resume)
    body = team_router.ChatRequest(
        request_id="immediate-adjustment", content="更换验证方法", timing="immediate"
    )
    await team_router.apply_adjustment(draft.name, body, draft, BackgroundTasks())
    assert "更换验证方法" in team.context_for(draft.name, "CoordinatorAgent")
    assert resume.await_args.args[1].node_id == "coordinator"


@pytest.mark.anyio
async def test_greeting_calls_model_without_starting_plan_or_paper(draft, monkeypatch):
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {"kind": "chat", "reply": "你好，我们接着讨论你的想法。"}
                )
            )
        )
    )
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    team.record(draft, "user", "chat", "我想研究交通流量")
    result = await project_router.prepare(draft, "你好！")
    assert result["message"] == "你好，我们接着讨论你的想法。"
    assert project_router.metadata(draft)["status"] == "chat"
    assert not project_router.metadata(draft).get("preflight")
    llm.chat.assert_awaited_once()
    context = json.loads(llm.chat.await_args.kwargs["history"][-1]["content"])
    assert context["latest_request"] == "你好！"
    assert context["conversation"][-1]["content"] == "我想研究交通流量"
    assert await paper_proposals.proposals(draft.name) == []
    assert not (draft / "paper").exists()
    assert not (draft / "workflow_state.json").exists()
    with pytest.raises(HTTPException):
        await project_router.start(draft, None, BackgroundTasks())


@pytest.mark.anyio
async def test_concept_question_is_chat_and_does_not_replace_existing_plan(
    draft, monkeypatch
):
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {"kind": "chat", "reply": "线性规划用于在线性约束下优化线性目标。"}
                )
            )
        )
    )
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    meta = project_router.metadata(draft)
    meta.update(status="ready", preflight={"id": "keep", "steps": ["比较基线"]})
    ws.write_json(draft / ".project.json", meta)
    result = await project_router.prepare(draft, "解释一下线性规划")
    assert "线性约束" in result["message"]
    assert project_router.metadata(draft)["preflight"]["id"] == "keep"
    assert project_router.metadata(draft)["status"] == "ready"
    assert not (draft / "workflow_state.json").exists()


@pytest.mark.anyio
async def test_create_records_actual_user_text(draft, monkeypatch):
    dispatch = AsyncMock()
    monkeypatch.setattr(team_router, "send_message", dispatch)
    result = await project_router.create_project(
        ques_all="你好",
        user_requirements="",
        execution_backend="python",
        comp_template="CHINA",
        competition_id="cumcm",
        competition_year=2026,
        paper_language="",
        competition_requirements="",
        files=[],
    )
    assert result["status"] == "chat"
    assert dispatch.await_args.args[1].content == "你好"


@pytest.fixture
def draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/draft-test"
    root.mkdir(parents=True)
    ws.write_json(
        root / ".project.json",
        {
            "status": "preparing",
            "title": "赛题",
            "attachments": [],
            "competition": competitions.select("cumcm", 2026),
            "problem": Problem(task_id=root.name, ques_all="预测温度").model_dump(),
        },
    )
    team_router._locks.clear()
    yield root
    modeling_router._scheduled_tasks.discard(root.name)


@pytest.mark.anyio
async def test_prepare_never_starts_solver_and_confirmation_checks_version(
    draft, monkeypatch
):
    response = SimpleNamespace(
        content=json.dumps(
            {
                "kind": "plan",
                "title": "温度预测",
                "understanding": "尚需训练数据",
                "steps": ["检查数据", "比较基线"],
                "questions": ["提供数据"],
            }
        )
    )
    llm = SimpleNamespace(chat=AsyncMock(return_value=response))
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    runner = AsyncMock()
    monkeypatch.setattr(modeling_router, "run_modeling_task_async", runner)
    await project_router.prepare(draft, "预读")
    assert not (draft / "workflow_state.json").exists()
    assert project_router.metadata(draft)["status"] == "needs_info"
    background = BackgroundTasks()
    with pytest.raises(HTTPException):
        await project_router.start(
            draft, project_router.metadata(draft)["preflight"]["id"], background
        )
    response.content = json.dumps(
        {
            "kind": "plan",
            "title": "温度预测",
            "understanding": "使用题目给定合成数据",
            "steps": ["先验证基线"],
            "questions": [],
        }
    )
    await project_router.prepare(draft, "根据题目参数生成明确标记的合成数据")
    with pytest.raises(HTTPException):
        await project_router.start(draft, "stale", background)
    assert not runner.called
    await project_router.start(
        draft, project_router.metadata(draft)["preflight"]["id"], background
    )
    assert not runner.called
    state = WorkflowCheckpoint(draft).load()
    assert "critical_review" in state["workflow_features"]
    assert "先验证基线" in state["problem"]["user_requirements"]
    await background()
    runner.assert_awaited_once()
    with pytest.raises(HTTPException):
        await project_router.start(
            draft, project_router.metadata(draft)["preflight"]["id"], BackgroundTasks()
        )


@pytest.mark.anyio
async def test_project_management_preserves_files_and_blocks_running_archive(draft):
    (draft / "input.csv").write_text("x\n1")
    await project_router.update_project(
        draft.name, project_router.ProjectUpdate(title="新项目名", archived=True)
    )
    assert (draft / "input.csv").exists()
    assert (await project_router.projects())[0]["archived"]
    await project_router.update_project(
        draft.name, project_router.ProjectUpdate(archived=False)
    )
    modeling_router._scheduled_tasks.add(draft.name)
    with pytest.raises(HTTPException):
        await project_router.update_project(
            draft.name, project_router.ProjectUpdate(archived=True)
        )


@pytest.mark.anyio
async def test_critical_gate_skips_ordinary_steps_but_keeps_model_results_and_failures(
    draft,
):
    checkpoint = WorkflowCheckpoint(draft)
    workflow = RemitWorkFlow()
    workflow.checkpoint = checkpoint
    workflow.work_dir = str(draft)
    for node, must_stop, report in [
        ("analysis", False, {}),
        ("pilot", False, {}),
        ("solve:ques1", False, {}),
        ("modeler", True, {}),
        ("review_results", True, {}),
        ("solve:ques1", True, {"status": "manual_review"}),
    ]:
        state = checkpoint.initialize(Problem(task_id=draft.name))
        state["workflow_features"].append("critical_review")
        state["completed_nodes"] = [node]
        if must_stop:
            with pytest.raises(WorkflowApprovalRequired):
                await workflow._require_human_approval(
                    state, node, summary="结果", quality_report=report
                )
        else:
            await workflow._require_human_approval(state, node, summary="结果")
            assert not state.get("pending_approval")


@pytest.mark.anyio
async def test_paper_proposal_requires_accept_and_checks_concurrent_edits(
    draft, monkeypatch
):
    root = writing_router._root(draft.name)
    original = "alpha\n中文🙂\nomega\n"
    (root / "main.tex").write_text(original, encoding="utf-8")
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps({"summary": "改选区", "replacement": "新内容\n"})
            )
        )
    )
    monkeypatch.setattr(paper_proposals.LLMFactory, "get_writer_llm", lambda self: llm)
    compile_mock = AsyncMock(return_value={"status": "completed"})
    monkeypatch.setattr(writing_router, "compile_source", compile_mock)
    result = await paper_proposals.propose(
        draft.name,
        "改这一段",
        {"name": "main.tex", "version": ws.digest(original), "start": 6, "end": 10},
    )
    assert (root / "main.tex").read_text(encoding="utf-8") == original
    proposal = (await paper_proposals.proposals(draft.name))[0]
    assert "-中文🙂" in proposal["diff"] and "+新内容" in proposal["diff"]
    await paper_proposals.decide(
        draft.name, result["proposal_id"], paper_proposals.Decision(accept=False)
    )
    assert (root / "main.tex").read_text(encoding="utf-8") == original
    assert not compile_mock.called
    result = await paper_proposals.propose(draft.name, "改全文", None)
    ws.save_source(root, "main.tex", original + "manual", ws.digest(original))
    with pytest.raises(HTTPException) as exc:
        await paper_proposals.decide(
            draft.name, result["proposal_id"], paper_proposals.Decision(accept=True)
        )
    assert exc.value.status_code == 409
    assert "manual" in (root / "main.tex").read_text(encoding="utf-8")
    result = await paper_proposals.propose(draft.name, "再改全文", None)
    await paper_proposals.decide(
        draft.name, result["proposal_id"], paper_proposals.Decision(accept=True)
    )
    compile_mock.assert_awaited_once()
    assert (root / "main.tex").read_text(encoding="utf-8") == "新内容\n"


@pytest.mark.parametrize("entry", competitions.catalog(), ids=lambda entry: entry["id"])
def test_every_contest_loads_pinned_skill_and_distinct_project_context(draft, entry):
    selected = competitions.select(entry["id"], 2026)
    ws.write_json(draft / ".project.json", {"competition": selected})
    context = competitions.context_for(draft.name, "WriterAgent")
    assert entry["name"] in context and entry["focus"] in context
    assert selected["skills"] and all(
        skill["content"] and skill["sha256"] for skill in selected["skills"]
    )
    source = competitions.template(draft)
    assert "\\begin{document}" in source and "\\end{document}" in source
    assert ("ctexart" in source) == (entry["language"] == "zh")


def test_future_rules_are_not_silently_reused_and_export_contains_review(draft):
    assert competitions.select("cumcm", 2027)["rules"].get("page_limit") is None
    assert competitions.select("cumcm", 2027)["rules_status"] == "needs_verification"
    root = writing_router._root(draft.name)
    source = (root / "main.tex").read_text(encoding="utf-8")
    assert "\\tableofcontents" not in source
    ws.save_source(
        root,
        "main.tex",
        source.replace("\\end{document}", "\\tableofcontents\n\\end{document}"),
        ws.digest(source),
    )
    assert any(
        check["status"] == "failed" for check in competitions.review(draft)["checks"]
    )
    notes = competitions.export_notes(draft)
    assert "submission/ai-usage-record.md" in notes
    assert "mcm.edu.cn" in notes["submission/checklist.md"]


def test_resume_cannot_bypass_critical_approval_when_global_hil_disabled(
    draft, monkeypatch
):
    from app.core.workflow import settings

    monkeypatch.setattr(settings, "HIL_ENABLED", False)
    checkpoint = WorkflowCheckpoint(draft)
    state = checkpoint.initialize(Problem(task_id=draft.name))
    state["workflow_features"].append("critical_review")
    state["completed_nodes"] = ["modeler"]
    checkpoint.request_approval(state, "modeler", summary="请确认方案")
    workflow = RemitWorkFlow()
    workflow.checkpoint = checkpoint
    with pytest.raises(WorkflowApprovalRequired):
        workflow._resolve_pending_approval_on_resume(state)
    assert checkpoint.load()["pending_approval"]


@pytest.mark.anyio
async def test_followup_attachments_preserve_inputs_and_invalidate_plan(
    draft, monkeypatch
):
    from app.services.task_intake import persist_uploads

    await persist_uploads(
        [UploadFile(filename="first.csv", file=BytesIO(b"x\n1"))], draft
    )
    meta = project_router.metadata(draft)
    meta.update(
        status="ready",
        attachments=["first.csv"],
        preflight={"id": "old", "questions": []},
    )
    ws.write_json(draft / ".project.json", meta)
    dispatch = AsyncMock()
    monkeypatch.setattr(team_router, "send_message", dispatch)
    await project_router.add_attachments(
        draft.name, [UploadFile(filename="second.custom", file=BytesIO(b"data"))]
    )
    assert json.loads((draft / ".remit-inputs.json").read_text()) == [
        "first.csv",
        "second.custom",
    ]
    assert project_router.metadata(draft)["status"] == "preparing"
    with pytest.raises(HTTPException):
        await project_router.start(draft, "old", BackgroundTasks())
    dispatch.assert_awaited_once()


@pytest.mark.anyio
async def test_folder_can_be_added_after_greeting_and_document_updates_problem(
    draft, monkeypatch
):
    dispatch = AsyncMock()
    monkeypatch.setattr(team_router, "send_message", dispatch)
    result = await project_router.add_attachments(
        draft.name,
        [UploadFile(filename="data.csv", file=BytesIO(b"x\n1"))],
        relative_paths=json.dumps(["dataset/train/data.csv"]),
        document_text="新的赛题全文",
    )
    assert result["files"] == ["dataset/train/data.csv"]
    assert "新的赛题全文" in project_router.metadata(draft)["problem"]["ques_all"]
    assert not (draft / "workflow_state.json").exists()
    dispatch.assert_awaited_once()
    from app.routers.files_router import get_files

    listing = await get_files(draft.name)
    assert "dataset/train/data.csv" in [item["filename"] for item in listing]
    assert not any(item["filename"].startswith(".") for item in listing)
    assert next(
        item for item in listing if item["filename"] == "dataset/train/data.csv"
    )["download_url"].endswith("/dataset/train/data.csv")


@pytest.mark.anyio
async def test_inputs_added_after_modeling_do_not_restart_or_replace_checkpoint(
    draft, monkeypatch
):
    checkpoint = WorkflowCheckpoint(draft)
    state = checkpoint.initialize(Problem(task_id=draft.name))
    checkpoint.start_node(state, "modeler")
    before = (draft / "workflow_state.json").read_bytes()
    dispatch = AsyncMock()
    monkeypatch.setattr(team_router, "send_message", dispatch)
    await project_router.add_attachments(
        draft.name, [UploadFile(filename="new.csv", file=BytesIO(b"x\n1"))]
    )
    assert (draft / "workflow_state.json").read_bytes() == before
    dispatch.assert_not_called()
    assert "new.csv" in team.context_for(draft.name, "CoderAgent")
    checkpoint._purge_solution_artifacts(
        ["ques1"], state, {"ques1": {"artifacts": ["new.csv"]}}
    )
    assert (draft / "new.csv").exists()


@pytest.mark.anyio
async def test_final_result_revision_returns_to_computation(draft, monkeypatch):
    checkpoint = WorkflowCheckpoint(draft)
    state = checkpoint.initialize(Problem(task_id=draft.name))
    state.update(
        questions={"ques1": "预测"},
        modeler_response={},
    )
    state["workflow_features"].append("critical_review")
    state["completed_nodes"] = checkpoint.node_order(state)
    pending = checkpoint.request_approval(state, "review_results", summary="验收结果")
    submit = AsyncMock(return_value=SimpleNamespace(message="重算"))
    monkeypatch.setattr(modeling_router, "submit_approval", submit)
    await team_router.execute_plan(
        draft.name,
        team_router.ChatRequest(
            request_id="revision-test",
            content="重新计算误差",
            checkpoint_id=pending["checkpoint_id"],
        ),
        team_router.Plan(action="revise", role="coder", instruction="重新计算误差"),
        draft,
        BackgroundTasks(),
    )
    assert submit.await_args.args[1].target_node_id == "solve:ques1"
