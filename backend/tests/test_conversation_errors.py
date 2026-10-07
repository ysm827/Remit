import asyncio

import pytest
from fastapi import HTTPException

from app.services.conversation_errors import explain


@pytest.mark.parametrize("status,expected", [(500, "HTTP 500"), (401, "密钥"), (429, "限流"), (404, "模型名称")])
def test_provider_body_never_enters_conversation(status, expected):
    error = RuntimeError("upstream body with private-token and request-id")
    error.status_code = status
    message = explain(error)
    assert expected in message
    assert "private-token" not in message
    assert "request-id" not in message


def test_timeout_and_safe_local_validation_remain_actionable():
    assert "超时" in explain(asyncio.TimeoutError())
    assert explain(HTTPException(409, "请先恢复归档项目。")) == "请先恢复归档项目。"
    assert "secret" not in explain(ValueError("secret"))
