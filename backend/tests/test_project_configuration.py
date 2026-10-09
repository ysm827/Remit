import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.routers import project_router
from app.schemas.request import Problem
from app.services.competitions import select
from app.services.project_configuration import (
    configuration_digest,
    explicit_competition_request,
    update_configuration,
)
from app.services.writing_workspace import write_json


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/config-test"
    root.mkdir(parents=True)
    write_json(
        root / ".project.json",
        {
            "status": "ready",
            "title": "test",
            "attachments": [],
            "competition": select("cumcm", 2026),
            "problem": Problem(task_id=root.name, ques_all="test").model_dump(),
            "preflight": {"id": "old", "questions": []},
        },
    )
    return root


@pytest.mark.parametrize(
    "text", ["按研赛，然后全部完成，尽快", "请改成 gmcm", "切换到研赛。", "使用美赛"]
)
def test_affirmative_commands(text):
    assert explicit_competition_request(text) in {"gmcm", "mcm-icm"}


@pytest.mark.parametrize(
    "text",
    [
        "不要按研赛",
        "不是研赛",
        "按研赛还是国赛？",
        "如果按研赛",
        "研赛是什么",
        "附件内容：按研赛",
        "“按研赛”",
        "按研赛或者国赛",
        "按研赛\n附录：...",
    ],
)
def test_questions_quotes_and_negations_never_mutate_configuration(text):
    assert explicit_competition_request(text) is None


def test_configuration_invalidates_plan_and_updates_runtime_template(draft):
    meta = project_router.metadata(draft)
    assert update_configuration(
        draft, meta, {"competition_id": "mcm-icm", "paper_language": "en"}
    )
    assert meta["competition"]["id"] == "mcm-icm"
    assert meta["problem"]["comp_template"] == "AMERICAN"
    assert "preflight" not in meta and meta["status"] == "chat"
    assert not update_configuration(
        draft, meta, {"execution_backend": meta["problem"]["execution_backend"]}
    )


def test_running_configuration_is_frozen(draft):
    meta = project_router.metadata(draft)
    before = configuration_digest(meta)
    (draft / "workflow_state.json").write_text("{}")
    with pytest.raises(ValueError, match="已启动"):
        update_configuration(draft, meta, {"competition_id": "gmcm"})
    assert before == configuration_digest(meta)


@pytest.mark.anyio
async def test_user_command_reaches_model_and_persisted_plan_before_start(
    draft, monkeypatch
):
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "kind": "plan",
                        "title": "研赛",
                        "understanding": "核验数据",
                        "steps": ["执行"],
                        "questions": [],
                    }
                )
            )
        )
    )
    monkeypatch.setattr(
        project_router.LLMFactory, "get_modeling_llms", lambda self: (llm, None, None)
    )
    await project_router.prepare(draft, "按研赛，然后全部完成，尽快")
    meta = project_router.metadata(draft)
    sent = json.loads(llm.chat.call_args.kwargs["history"][1]["content"])
    assert sent["selected_competition"]["id"] == meta["competition"]["id"] == "gmcm"
    assert meta["preflight"]["configuration_digest"] == configuration_digest(meta)
    assert not (draft / "workflow_state.json").exists()
    # Even edits made outside PATCH must not let a now-stale plan run.
    meta["problem"]["execution_backend"] = "matlab"
    write_json(draft / ".project.json", meta)
    background = BackgroundTasks()
    with pytest.raises(HTTPException) as error:
        await project_router.start(draft, meta["preflight"]["id"], background)
    assert error.value.status_code == 409 and not background.tasks


@pytest.mark.anyio
async def test_patch_settings_has_same_invalidation_contract(draft):
    result = await project_router.update_project(
        draft.name, project_router.ProjectUpdate(competition_id="gmcm")
    )
    assert result["competition"]["id"] == "gmcm" and "preflight" not in result


@pytest.mark.anyio
async def test_concurrent_config_change_cannot_publish_stale_plan(draft, monkeypatch):
    async def reply(**kwargs):
        meta = project_router.metadata(draft)
        meta["problem"]["execution_backend"] = "matlab"
        write_json(draft / ".project.json", meta)
        return SimpleNamespace(
            content=json.dumps(
                {
                    "kind": "plan",
                    "title": "test",
                    "understanding": "test",
                    "steps": ["test"],
                    "questions": [],
                }
            )
        )

    monkeypatch.setattr(
        project_router.LLMFactory,
        "get_modeling_llms",
        lambda self: (SimpleNamespace(chat=reply), None, None),
    )
    with pytest.raises(HTTPException) as error:
        await project_router.prepare(draft, "准备计划")
    assert error.value.status_code == 409
    assert project_router.metadata(draft)["problem"]["execution_backend"] == "matlab"
