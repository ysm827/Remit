import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.agents.modeler_agent import ModelerAgent
from app.core.deliverable_contract import (
    build_stage_contract,
    collect_model_quality_evidence,
    _stage_execution_preview,
)
from app.core.llm.types import StandardResponse
from app.tools.notebook_serializer import NotebookSerializer
from app.utils.notebook_text import notebook_output_text


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_real_notebook_output_and_legacy_html_remain_readable(tmp_path):
    serializer = NotebookSerializer(str(tmp_path))
    serializer.add_markdown_segmentation_to_notebook("实际阶段", "eda")
    serializer.add_code_cell_to_notebook("print('核验通过 Sxx=17.5')")
    serializer.add_code_cell_output_to_notebook("核验通过 Sxx=17.5\ny=[1,3,5,7,9,11]\n")
    current = _stage_execution_preview(tmp_path, "eda")
    assert "核验通过 Sxx=17.5" in current[-1]["output"]
    notebook = json.loads((tmp_path / "notebook.ipynb").read_text(encoding="utf-8"))
    del notebook["cells"][-1]["outputs"][0]["data"]["text/plain"]
    (tmp_path / "notebook.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    legacy = _stage_execution_preview(tmp_path, "eda")
    assert legacy[-1]["output"] == current[-1]["output"].strip()
    assert ".body_background" not in legacy[-1]["output"]


def test_html_evidence_is_plain_text_not_script_or_style():
    assert (
        notebook_output_text(
            {
                "data": {
                    "text/html": "<head><style>secret_css</style></head><script>do_something()</script><pre>a &lt; b\n2</pre>"
                }
            }
        )
        == "a < b\n2"
    )
    assert (
        notebook_output_text(
            {"data": {"text/plain": ["plain", " evidence"], "text/html": "ignored"}}
        )
        == "plain evidence"
    )


def test_eda_evidence_has_current_artifacts_without_false_prediction_gap(tmp_path):
    (tmp_path / "eda").mkdir()
    (tmp_path / "eda/structure_check.json").write_text(
        '{"y_full_sequence":[1,3,5,7,9,11],"all_passed":true}', encoding="utf-8"
    )
    (tmp_path / "eda_struct.py").write_text(
        'df = pd.read_csv("observed.csv")', encoding="utf-8"
    )
    (tmp_path / "eda_quality_report.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    "eda/structure_check.json",
                    "eda_struct.py",
                    "../outside.json",
                ]
            }
        ),
        encoding="utf-8",
    )
    result = collect_model_quality_evidence(tmp_path, build_stage_contract("eda"))
    assert "prediction_metrics" not in result
    assert result["stage_scope"]["requires_prediction_values"] is False
    assert (
        "y_full_sequence"
        in result["supporting_artifact_previews"]["eda/structure_check.json"]["content"]
    )
    assert (
        "read_csv" in result["supporting_artifact_previews"]["eda_struct.py"]["source"]
    )
    assert "../outside.json" not in result["supporting_artifact_previews"]


@pytest.mark.anyio
async def test_review_sends_current_scope_not_earlier_stage_transcripts():
    agent = ModelerAgent("review-scope", MagicMock())
    agent.chat_history = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": "obsolete_stage_transcript" * 1000},
    ]
    payload = {
        "verdict": "accept",
        "summary": "已核对本阶段结构与实际文件，后续求解尚未开始。",
        "evidence": ["six actual rows"],
        "strengths": ["结构核验完成"],
        "weaknesses": ["仅覆盖数据检查"],
        "writer_guidance": "仅描述已有数据证据，尚未开始的求解不作结论。",
        "revision_plan": None,
    }
    agent._chat = AsyncMock(return_value=StandardResponse(content=json.dumps(payload)))
    result = await agent.review_execution_result(
        question_key="eda",
        question_text="结构核验",
        current_plan="读取数据",
        evidence={"stage_scope": {"requires_prediction_values": False}},
        rejected_models=[],
        remaining_runs=1,
        task_purpose="numerical_verification",
        task_constraints="指定 OLS，不改方法",
    )
    assert result.verdict == "accept"
    sent = agent._chat.await_args.kwargs["history"]
    assert "obsolete_stage_transcript" not in json.dumps(sent)
    request = json.loads(sent[-1]["content"])
    assert request["task_constraints"] == "指定 OLS，不改方法"
    assert request["task_purpose"] == "numerical_verification"
    assert (
        request["execution_evidence"]["stage_scope"]["requires_prediction_values"]
        is False
    )
