import pytest

from app.core.deliverable_contract import (
    DeliverableValidationError,
    collect_grounding_values,
    validate_writer_section,
)


def section(number):
    return (
        f"优化模型按公式 $E=pt$ 求解，最大相对误差为 {number}。"
        + "所用参数来源于执行记录，并按相同单位核对。" * 40
    )


@pytest.mark.parametrize(
    "number", ["3.2935566501868934e-14", "3.294E-14", "+3.2935566501868934e-14"]
)
def test_scientific_notation_is_one_grounded_number(number):
    validate_writer_section(
        "ques1", section(number), grounding_values={3.2935566501868934e-14}
    )


@pytest.mark.parametrize("number", ["3.294e-10", "1e-6", "9e999"])
def test_scientific_notation_does_not_relax_precision_or_small_integer_rules(number):
    with pytest.raises(DeliverableValidationError, match="找不到来源"):
        validate_writer_section(
            "ques1", section(number), grounding_values={3.2935566501868934e-14}
        )


def test_grounding_extraction_keeps_exponent_and_interval_endpoints():
    values = collect_grounding_values(
        {"text": "误差3.293e-14，区间0.75-0.85，偏差-0.2"}
    )
    assert values == {3.293e-14, 0.75, 0.85, -0.2}
