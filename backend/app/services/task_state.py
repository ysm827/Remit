"""任务生命周期的线协议与旧版消息兼容规则。"""

import json
from typing import Literal

TaskStatus = Literal["running", "awaiting_approval", "completed", "failed", "stopped"]
TASK_STATUSES = {"running", "awaiting_approval", "completed", "failed", "stopped"}


def message_task_status(message: dict) -> TaskStatus | None:
    """优先读取结构化状态；仅对旧档案兼容历史中文文案。"""
    explicit = message.get("task_status")
    if isinstance(explicit, str) and explicit in TASK_STATUSES:
        return explicit
    if message.get("msg_type") == "approval":
        return "awaiting_approval"
    if message.get("msg_type") != "system":
        return None
    kind, content = message.get("type"), str(message.get("content", ""))
    if kind == "success" and content == "任务处理完成":
        return "completed"
    if kind == "error" and content.startswith("任务执行失败"):
        return "failed"
    if kind == "warning" and ("任务已停止" in content or "服务重启" in content):
        return "stopped"
    if content == "任务开始处理" or content.startswith(
        ("任务从节点 ", "任务继续处理", "自动续跑开始")
    ):
        return "running"
    return None


def task_status_from_messages(messages: list[dict]) -> TaskStatus:
    """返回最后一次显式生命周期变化，普通进度不能改变终态。"""
    for message in reversed(messages):
        if status := message_task_status(message):
            return status
    return "running"


def message_title(message: dict) -> tuple[str, int]:
    """提取索引标题与优先级，优先保留第一条非空用户题目。"""
    content = str(message.get("content") or "").strip()
    if message.get("msg_type") == "user" and content:
        return " ".join(content.split())[:80], 2
    if message.get("agent_type") == "CoordinatorAgent":
        try:
            payload = json.loads(content.replace("```json", "").replace("```", ""))
        except (ValueError, TypeError):
            return "", 0
        if isinstance(payload, dict) and payload.get("title"):
            return " ".join(str(payload["title"]).split())[:80], 1
    return "", 0
