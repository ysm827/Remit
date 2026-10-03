import pytest

from app.core.deliverable_contract import build_question_contract


def test_unfinished_computation_has_room_to_debug_but_format_repairs_stay_small(
    tmp_path,
):
    from app.core.deliverable_contract import get_repair_execution_limit

    contract = build_question_contract("ques1", "运输方案优化")
    assert get_repair_execution_limit(tmp_path, contract) == 4
    (tmp_path / "ques1_routes.csv").write_text("route,energy\n1,2\n")
    assert get_repair_execution_limit(tmp_path, contract) == 2


@pytest.mark.parametrize(
    "question",
    [
        "单点往返运输能力与货箱组批，计算最大安全载荷，优化架次数、能耗和时间",
        "根据通信状态判定链路可用性，优化运输与中继联合调度",
        "救援任务分区与资源配置优化方案，识别库存缺口",
    ],
)
def test_shared_plan_and_constraint_verbs_cannot_turn_optimization_into_classifier(
    question,
):
    contract = build_question_contract(
        "ques1",
        question,
        '用户确认的初始执行计划：{"检查":"识别缺失字段，判定通信条件","方法":"优化运输"}',
    )
    assert contract.problem_type == "optimization"
    assert not contract.requires_prediction_values
    assert "逐样本独立验证契约" not in contract.prompt_block()
    assert "type_specific" in contract.prompt_block()


@pytest.mark.parametrize(
    "question,requirements,expected",
    [
        ("训练分类模型判定疾病", "优化模型参数", "classification"),
        ("拟合浓度与温度的关系", "判定附件是否可读", "regression"),
        ("构建综合评价体系", "识别重复记录", "evaluation"),
        ("分析当前数据", "问题1建立分类模型", "classification"),
        ("分析当前数据", "问题2建立分类模型", "analysis"),
    ],
)
def test_predictive_tasks_and_scoped_requirements_remain_supported(
    question, requirements, expected
):
    assert (
        build_question_contract("ques1", question, requirements).problem_type
        == expected
    )
