"""Explicit numeric scope retains evidence checks without inventing OOF data."""

import json
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.deliverable_contract import (
    DeliverableValidationError,
    build_question_contract,
    build_stage_contract,
    validate_question_deliverables,
)
from app.core.flows import Flows
from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.schemas.A2A import ModelerToCoder
from app.schemas.request import Problem


@pytest.mark.parametrize("purpose", ["modeling", "numerical_verification"])
def test_selected_plan_scope_reaches_real_agent_request(purpose):
    from app.core.agents.modeler_agent import ModelerAgent
    from app.core.llm.types import StandardResponse
    from app.core.prompts.modeler import get_modeler_prompt, MODELER_PROMPT
    from app.schemas.A2A import CoordinatorToModeler

    plan = {
        key: "指定方法与实际输入；独立复算系数和残差，保留容差及证据；失败只修受影响步骤。"
        * 2
        for key in ["eda", "ques1", "sensitivity_analysis"]
    }
    model = AsyncMock()
    model.max_tokens = 4096
    model.chat.return_value = StandardResponse(content=json.dumps(plan))
    prompt = get_modeler_prompt(purpose)
    agent = ModelerAgent("plan-scope", model, system_prompt=prompt)
    result = asyncio.run(
        agent.run(
            CoordinatorToModeler(
                questions={"ques1": "按指定方法核验"},
                ques_count=1,
                user_requirements="保留原容差及输入",
                task_purpose=purpose,
            )
        )
    )
    assert result.questions_solution == plan
    request = model.chat.await_args.kwargs["history"]
    assert request[0] == {"role": "system", "content": prompt}
    assert json.loads(request[1]["content"])["task_purpose"] == purpose
    if purpose == "modeling":
        assert prompt == MODELER_PROMPT
    else:
        assert "选模决策树" not in prompt and "必出核心图" not in prompt
        assert "独立复算" in prompt and "对应计算步骤结束前落盘" in prompt
        assert len(prompt) < len(MODELER_PROMPT)
    with pytest.raises(ValueError):
        get_modeler_prompt("bypass")


def test_only_explicit_numeric_purpose_changes_contract():
    text = "软件验收：仅六行合成数据，用 OLS 拟合并独立复算"
    default = build_question_contract("ques1", text)
    assert default.requires_prediction_values
    assert default.minimum_candidate_models == 2
    numeric = build_question_contract(
        "ques1", text, task_purpose="numerical_verification"
    )
    assert not numeric.requires_prediction_values
    assert not numeric.minimum_candidate_models
    assert numeric.minimum_robustness_checks == 2
    assert "不做候选选型" in numeric.prompt_block()
    with pytest.raises(ValueError):
        build_question_contract("ques1", text, task_purpose="bypass")


@pytest.fixture
def numeric_case(tmp_path):
    (tmp_path / "observed.csv").write_text("x,y\n0,1\n1,3\n", encoding="utf-8")
    (tmp_path / "verification.csv").write_text(
        "name,actual,reference,atol,rtol\nslope,2,2,1e-10,0\nintercept,1,1,1e-10,0\n",
        encoding="utf-8",
    )
    report = {
        "status": "pass",
        "problem_type": "numerical_verification",
        "selected_model": "OLS",
        "candidate_models": [],
        "robustness_checks": [
            {"name": "formula", "passed": True},
            {"name": "leave-one-out", "passed": True},
        ],
        "limitations": ["given input consistency only, no generalization"],
        "artifacts": ["verification.csv"],
        "paper_ready_images": [],
        "type_specific": {
            "metric_scope": "given_inputs_only",
            "generalization_verified": False,
            "input_files": ["observed.csv"],
            "verification_file": "verification.csv",
            "reference_method": "Independent closed-form centered sums",
            "tolerance_source": "Approved absolute coefficient tolerance 1e-10",
        },
    }
    return (
        tmp_path,
        report,
        build_question_contract("ques1", "OLS", task_purpose="numerical_verification"),
    )


def validate(case):
    root, report, contract = case
    (root / contract.quality_filename).write_text(json.dumps(report), encoding="utf-8")
    return validate_question_deliverables(root, contract)


def test_numeric_consistency_passes_without_claiming_prediction(numeric_case):
    result = validate(numeric_case)
    assert result.passed
    assert result.prediction_rows == 0
    assert result.primary_metric_name is None


@pytest.mark.parametrize(
    "row",
    [
        "slope,2,3,1e-10,0",
        "slope,nan,2,1e-10,0",
        "slope,2,2,-1,0",
        "slope,2,2,0,inf",
        "slope,2,2,1e308,1e308",
        ",2,2,1e-10,0",
        "",
    ],
)
def test_recompute_disagrees_with_self_declared_pass(numeric_case, row):
    root = numeric_case[0]
    (root / "verification.csv").write_text(
        "name,actual,reference,atol,rtol\n" + row, encoding="utf-8"
    )
    with pytest.raises(DeliverableValidationError):
        validate(numeric_case)


@pytest.mark.parametrize(
    "field,value",
    [
        ("metric_scope", "independent_test"),
        ("generalization_verified", True),
        ("input_files", []),
        ("input_files", ["missing.csv"]),
        ("verification_file", "../outside.csv"),
        ("reference_method", ""),
        ("tolerance_source", ""),
    ],
)
def test_numeric_scope_requires_real_files_and_explicit_boundary(
    numeric_case, field, value
):
    numeric_case[1]["type_specific"][field] = value
    with pytest.raises(DeliverableValidationError):
        validate(numeric_case)


def test_scientific_default_cannot_accept_numeric_report(numeric_case):
    root, report, _ = numeric_case
    with pytest.raises(DeliverableValidationError):
        validate((root, report, build_question_contract("ques1", "拟合实际观测值")))


def test_scope_reaches_all_solver_prompts():
    flow = Flows({"ques1": "OLS 拟合"}, task_purpose="numerical_verification")
    stages = flow.get_solution_flows(
        flow.questions, ModelerToCoder(questions_solution={"ques1": "指定 OLS"})
    )
    assert stages["ques1"]["contract"].problem_type == "numerical_verification"
    assert "独立复算" in stages["ques1"]["coder_prompt"]
    sensitivity = stages["sensitivity_analysis"]
    assert sensitivity["contract"].problem_type == "numerical_verification"
    assert "3个扰动场景" not in sensitivity["coder_prompt"]
    assert "复用已有计算与独立复算证据" in sensitivity["coder_prompt"]
    for key in ("eda", "sensitivity_analysis"):
        assert "不评定泛化能力" in stages[key]["coder_prompt"]
    assert all(
        stage["contract"].task_purpose == "numerical_verification"
        for stage in stages.values()
    )
    eda = stages["eda"]
    assert eda["contract"].problem_type == "eda"
    assert "不默认清洗" in eda["coder_prompt"]
    assert "数据清洗,可视化" not in eda["coder_prompt"]
    assert "机理题可将" not in eda["coder_prompt"]
    assert "数据驱动题六项必须真实完成" in build_stage_contract("eda").prompt_block()


@pytest.mark.parametrize("language", ["python", "matlab"])
def test_numeric_coder_avoids_generic_figure_quota(language, tmp_path):
    from unittest.mock import Mock
    from app.core.agents.coder_agent import CoderAgent
    from app.core.prompts.coder import get_coder_prompt

    interpreter = Mock(language=language)
    model = Mock(max_tokens=4096)
    agent = CoderAgent(
        "numeric-scope",
        model,
        str(tmp_path),
        code_interpreter=interpreter,
        task_purpose="numerical_verification",
    )
    prompt = get_coder_prompt(language, "numerical_verification")
    assert agent.system_prompt == prompt
    assert f"执行语言：{language}" in prompt
    assert "独立复算不得调用主实现" in prompt
    assert "出图量级" not in prompt and "IQR" not in prompt
    assert "质量报告" in prompt and "不默认删行" in prompt
    with pytest.raises(ValueError):
        get_coder_prompt(language, "bypass")


def test_numeric_stability_reuses_evidence_but_rejects_wrong_values(numeric_case):
    root, report, _ = numeric_case
    contract = build_stage_contract("sensitivity_analysis", "numerical_verification")
    assert validate((root, report, contract)).passed
    (root / "verification.csv").write_text(
        "name,actual,reference,atol,rtol\nslope,2,3,1e-10,0\n", encoding="utf-8"
    )
    with pytest.raises(DeliverableValidationError):
        validate((root, report, contract))
    assert build_stage_contract("sensitivity_analysis").problem_type == "sensitivity"
    assert "3个扰动场景" in build_stage_contract("sensitivity_analysis").prompt_block()
    with pytest.raises(ValueError):
        build_stage_contract("sensitivity_analysis", "bypass")


def test_retiring_pilot_archives_protocol_files_and_preserves_inputs(tmp_path):
    protected = tmp_path / "pilot_ques2_results.json"
    protected.write_text("user attachment", encoding="utf-8")
    cp = WorkflowCheckpoint(tmp_path)
    state = cp.initialize(Problem(task_id="archive"))
    generated = {
        "pilot_results.json": "combined",
        "pilot_ques1_results.json": "partial",
        "final_citations.json": "citations",
    }
    for name, value in generated.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    cp.retire_pilot_outputs(state)
    assert protected.read_text(encoding="utf-8") == "user attachment"
    for name, value in generated.items():
        assert not (tmp_path / name).exists()
        archived = list((tmp_path / ".history").glob(f"*/{name}"))
        assert len(archived) == 1
        assert archived[0].read_text(encoding="utf-8") == value
    cp.retire_pilot_outputs(state)
    assert len(list((tmp_path / ".history").iterdir())) == 1
