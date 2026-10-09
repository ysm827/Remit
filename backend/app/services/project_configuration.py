"""One authoritative configuration for intake, approved plans and execution."""

import hashlib
import json
import re
from pathlib import Path

from app.services.competitions import catalog, select


def configuration_digest(meta: dict) -> str:
    """Exclude presentation/status fields; include everything the plan executes."""
    payload = {key: meta.get(key) for key in ("competition", "problem", "attachments")}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def explicit_competition_request(request: str) -> str | None:
    """Recognize only an affirmative, leading user command, never quoted evidence.

    This is intentionally not an NLP classifier: questions, negations,
    alternatives and long pasted material stay with the planning clarification.
    The structured PATCH API covers all catalog entries without inference.
    """
    text = request.strip()
    if len(text) > 200 or re.search(
        r"[?？\n\r]|不要|别|不是|是否|如果|假如|还是|或者|或是", text
    ):
        return None
    aliases = {entry["id"].lower(): entry["id"] for entry in catalog()}
    aliases.update(
        {"国赛": "cumcm", "研赛": "gmcm", "研究生数模竞赛": "gmcm", "美赛": "mcm-icm"}
    )
    match = re.match(
        r"^(?:请)?(?:按|改成|改为|切换到|赛事改为|就用|使用)\s*(?:赛事\s*)?"
        r"("
        + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
        + r")(?:$|[，,。；;\s]|来|进行|执行)",
        text,
        re.I,
    )
    if not match:
        return None
    selected = aliases[match.group(1).lower()]
    # A second named competition makes the command ambiguous.
    remainder = text[match.end(1) :].lower()
    if any(alias in remainder for alias in aliases):
        return None
    return selected


def update_configuration(root: Path, meta: dict, changes: dict) -> bool:
    """Mutate metadata in memory atomically; caller persists under task lock."""
    if not changes:
        return False
    if meta.get("archived") or (root / "workflow_state.json").exists():
        raise ValueError(
            "项目已启动或归档，不能更改已执行配置；请在新项目中重新确认计划。"
        )
    old = meta.get("competition", {})
    competition_fields = {
        "competition_id",
        "competition_year",
        "paper_language",
        "competition_requirements",
    }
    candidate = dict(meta)
    problem = dict(meta["problem"])
    if competition_fields.intersection(changes):
        competition = select(
            changes.get("competition_id", old.get("id", "cumcm")),
            changes.get("competition_year", old.get("year", 2026)),
            changes.get("paper_language", old.get("language", "")),
            changes.get("competition_requirements", old.get("user_requirements", "")),
        )
        candidate["competition"] = competition
        problem["comp_template"] = competition["template"]
    for key in ("execution_backend", "task_purpose", "literature_enabled"):
        if key in changes:
            problem[key] = changes[key]
    candidate["problem"] = problem
    if configuration_digest(meta) == configuration_digest(candidate):
        return False
    candidate.pop("preflight", None)
    candidate["status"] = "chat"
    meta.clear()
    meta.update(candidate)
    return True
