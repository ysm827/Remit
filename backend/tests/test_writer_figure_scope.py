import pytest

from app.core.deliverable_contract import (
    DeliverableValidationError,
    validate_writer_section,
)


def test_other_section_figure_feedback_identifies_scope_not_reason_length():
    with pytest.raises(DeliverableValidationError) as caught:
        validate_writer_section(
            "ques1",
            "指定输入的计算结果见图，结论仅限给定数据。" * 35
            + "\n\n![拟合结果](fit.png)\n",
            required_images=["fit.png"],
            omitted_images={
                "other_section.png": "其他阶段的补充图已保留在稳定性章节，正文以表格说明。"
            },
            mode="short_report",
        )
    detail = str(caught.value)
    assert "不属于本节候选图片" in detail
    assert "请删除" in detail
    assert "本节候选仅有：fit.png" in detail
    assert "请说明替代证据与保留位置" not in detail
