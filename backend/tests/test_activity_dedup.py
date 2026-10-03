from app.services.team_state import events, record


def test_repeated_streaming_activity_does_not_grow_history(tmp_path):
    for i in range(100):
        record(
            tmp_path,
            "coder",
            "activity",
            "代码手正在输出…",
            {"created_at": str(i), "category": "llm"},
        )
    assert len(events(tmp_path)) == 1
    record(
        tmp_path, "coder", "activity", "代码报错，正在自动修复", {"category": "repair"}
    )
    record(tmp_path, "coder", "activity", "代码手正在输出…", {"category": "llm"})
    assert len(events(tmp_path)) == 3


def test_changed_detail_and_real_tool_calls_are_never_deduplicated(tmp_path):
    for detail in ["first", "second"]:
        record(tmp_path, "coder", "activity", "校验", {"detail": detail})
        record(tmp_path, "coder", "tool", "execute_code", {"input": {"code": "a=1"}})
    assert len(events(tmp_path)) == 4
