"""从当前证据生成轻量章节计划，不增加模型调用，也不补造研究事实。"""

import json

from app.core.task_purpose import NUMERICAL_VERIFICATION_SCOPE


def build_plan(evidence: dict) -> list[dict]:
    """按小问列出已有内容与缺口，保留负结果和验证状态。"""
    model = evidence.get("modeler_response") or {}
    solutions = model.get("questions_solution") or {}
    questions = evidence.get("questions") or {}
    sections = []
    for key, result in (evidence.get("solution_results") or {}).items():
        sections.append(
            {
                "key": key,
                "question": result.get("question_text")
                or questions.get(key, "尚未记录问题文本"),
                "model": solutions.get(key)
                or "尚未记录独立模型说明，须从已确认方案核对",
                "results": result.get("execution_summary")
                or "尚无结构化结果摘要，请核对证据文件",
                "evidence_files": result.get("artifacts") or [],
                "figures": result.get("paper_ready_images") or [],
                "validation": result.get("quality_report") or {"status": "unknown"},
                "limitations": (result.get("model_review") or {}).get("weaknesses")
                or "仅报告证据支持的适用范围；没有对照实验不得声称提升",
            }
        )
    return sections


def section_context(key: str, evidence: dict, notes: str = "") -> str:
    """同一快照下的章节输入，同时约束符号、数值和图表引用。"""
    sections = build_plan(evidence)
    selected = [section for section in sections if section["key"] == key]
    context = {
        "section": selected or sections,
        "artifact_hashes": evidence.get("artifact_hashes") or {},
        "editorial_notes": notes,
    }
    purpose = (evidence.get("problem") or {}).get("task_purpose", "modeling")
    boundary = ""
    if purpose == "numerical_verification":
        boundary = (
            NUMERICAL_VERIFICATION_SCOPE
            + "区分理论精确值与浮点实测残差。数值和差值以原始 CSV/JSON 精度为准，"
            "非零微小差不能因显示舍入而写成零；图内舍入标注只能说明近似一致。"
            "逐折范围须注明实现路径；极差是最大值减最小值，不能用系数值替代。"
            "有限的变更输入测试只支持已覆盖情形，"
            "不能写成普遍排除硬编码的证明。小样本不自动意味着所有统计量无意义；"
            "应依据数据生成过程、验证设计和题目范围说明推断限制。"
            "不能从复核状态推导出尚未完成的独立科学验收。\n"
        )
    return (
        "\n【已保存的章节计划与事实边界】\n"
        "按问题、模型选择理由、求解、证据、解释、局限组织论证；不要机械重复标题。"
        "关键数值必须注明证据文件、口径与单位；缺失项写明缺口，不从局部样本推断整体。"
        "跨章保持模型名称、符号及单位一致；摘要最后只总结实际完成内容。"
        "编辑意见不改变科学证据；需要新实验时明确依赖，不编造补全。\n"
        + boundary
        + json.dumps(context, ensure_ascii=False, default=str)
    )
