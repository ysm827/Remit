"""Explicit task intent; report length never changes scientific requirements."""

from typing import Literal

TaskPurpose = Literal["modeling", "numerical_verification"]

NUMERICAL_VERIFICATION_SCOPE = (
    "用户明确选择了指定计算与数值核验：只执行题目指定的方法与真实输入，"
    "验证计算正确性、可复现性和适用边界。不得为了候选比较改变指定方法，"
    "不得补造样本以满足预测验证条数，不评定泛化能力或模型优越性。"
    "若题目实际要求预测性能或尚未确定方法，必须说明目标冲突，不能按此模式宣称通过。"
)
