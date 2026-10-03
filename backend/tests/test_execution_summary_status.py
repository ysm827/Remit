import pytest

from app.core.execution_summary import build_execution_summary_message
from app.schemas.A2A import ModelExecutionReview


@pytest.mark.parametrize("verdict", ["accept", "manual_review"])
def test_summary_text_agrees_with_actual_review(tmp_path, verdict):
    review = ModelExecutionReview(
        verdict=verdict,
        summary="已保存真实计算结果，按当前阶段的实际证据给出复核结论。",
        evidence=["result.csv"],
        strengths=["已保存结果"],
        weaknesses=["固定小样本"],
        writer_guidance="正文只引用已经保存并能回读的证据。",
        revision_plan=None,
    )
    message = build_execution_summary_message(
        task_id="summary-check",
        node_id="solve:ques1",
        node_label="问题1",
        section="ques1",
        work_dir=tmp_path,
        evidence={"quality_report": {"selected_model": "OLS"}},
        review=review,
        revision_count=0,
        artifacts=["result.csv"],
        paper_ready_images=[],
    )
    assert message.content == message.run_summary
    assert "独立质量校验" not in message.content
    if verdict == "manual_review":
        assert message.status == "needs_review"
        assert "仍需核验" in message.content
        assert "通过" not in message.content
    else:
        assert message.status == "passed"
        assert "通过自动检查和建模手复核" in message.content
