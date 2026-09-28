"""Reusable HTTP-boundary validation helpers."""

from fastapi import HTTPException, WebSocket

from app.utils.common_utils import ensure_safe_task_id


def http_task_id(raw: str) -> str:
    """Convert a path/query value into a validated task identifier."""
    try:
        return ensure_safe_task_id(raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="任务编号格式不正确") from error


async def websocket_task_id(websocket: WebSocket, raw: str) -> str | None:
    """Validate a WebSocket task id and close policy violations at the boundary."""
    try:
        return ensure_safe_task_id(raw)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid task id")
        return None
