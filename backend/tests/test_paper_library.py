import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.llm.types import StandardResponse, Usage
from app.services import paper_library as library


@pytest.fixture
def anyio_backend():
    return "asyncio"


def payload():
    return {
        "topic": "调度优化",
        "patterns": [
            {
                "lesson": "明确模型目标和现实约束",
                "application": "本项目需用实测可行性检查支持目标值",
                "evidence_page": 1,
                "evidence_quote": "先定义目标与约束再比较结果",
            },
            {
                "lesson": "说明参数变化对结论的影响",
                "application": "使用本项目真实扰动实验解释适用范围",
                "evidence_page": 1,
                "evidence_quote": "参数变化之后比较方案的稳定性",
            },
        ],
    }


def record():
    return {
        "metadata": {
            "id": "example",
            "sha256": "abc",
            "sources": ["sample.pdf"],
            "competition": "gmcm",
            "pages": 1,
            "marker_pages": {},
        },
        "pages": ["先定义目标与约束再比较结果。参数变化之后比较方案的稳定性。"],
    }


def model_payload():
    output = payload()
    evidence_id = next(iter(library.evidence_passages(library.sample_pages(record()))))
    for pattern in output["patterns"]:
        pattern.pop("evidence_page")
        pattern.pop("evidence_quote")
        pattern["evidence_id"] = evidence_id
    return output


def test_evidence_ids_preserve_exact_source_and_reject_unknown_ids():
    sampled = library.sample_pages(record())
    passages = library.evidence_passages(sampled)
    resolved = library.resolve_evidence(model_payload(), passages)
    checked = library.validate_card(resolved, sampled)
    assert checked["patterns"][0]["evidence_quote"] == record()["pages"][0]
    invalid = model_payload()
    invalid["patterns"][0]["evidence_id"] = "p999s1"
    with pytest.raises(ValueError, match="Unknown evidence_id"):
        library.resolve_evidence(invalid, passages)


def test_long_pages_split_without_inventing_or_skipping_evidence():
    page = ("这是用于检验原文片段编号的长句。" * 250) + "末尾原文片段保留。"
    passages = library.evidence_passages({7: page})
    assert "".join(p["text"] for p in passages.values()) == page
    assert all(8 <= len(p["text"]) <= 220 and p["page"] == 7 for p in passages.values())


def test_rejects_invented_quotes_and_unseen_pages():
    sampled = library.sample_pages(record())
    assert len(library.validate_card(payload(), sampled)["patterns"]) == 2
    changed = payload()
    changed["patterns"][0]["evidence_quote"] = "不存在的句子不能作为证据"
    with pytest.raises(ValueError, match="not present"):
        library.validate_card(changed, sampled)
    changed = payload()
    changed["patterns"][0]["evidence_page"] = 8
    with pytest.raises(ValueError, match="not supplied"):
        library.validate_card(changed, sampled)


@pytest.mark.anyio
async def test_truncated_distillation_retries_once_and_saves_diagnostics(tmp_path):
    llm = SimpleNamespace(
        model="test",
        chat=AsyncMock(
            side_effect=[
                StandardResponse(
                    content=None,
                    finish_reason="length",
                    usage=Usage(completion_tokens=8192),
                ),
                StandardResponse(
                    content=json.dumps(model_payload()), finish_reason="stop"
                ),
            ]
        ),
    )
    card = await library.distill_one(record(), llm, tmp_path / "audit.json")
    assert card["coverage"] == "selected_pages"
    assert card["grounding"] == "exact_quote_verified"
    assert [call.kwargs["max_tokens"] for call in llm.chat.await_args_list] == [
        8192,
        16384,
    ]
    assert len(json.loads((tmp_path / "audit.json").read_text())) == 2


def test_portable_context_needs_no_source_pdfs(tmp_path, monkeypatch):
    root = tmp_path / "a different install" / "writing"
    (root / "contests").mkdir(parents=True)
    (root / "SKILL.md").write_text("Common writing lessons", encoding="utf-8")
    (root / "contests/gmcm.md").write_text("GMCM specific", encoding="utf-8")
    (root / "library.json").write_text(
        json.dumps(
            {
                "cards": [
                    {"competition": "gmcm", "topic": "Matching exemplar"},
                    {"competition": "cumcm", "topic": "Other contest exemplar"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(library, "LIBRARY_ROOT", root)
    context = library.context("gmcm")
    assert "Matching exemplar" in context and "GMCM specific" in context
    assert "Other contest exemplar" not in context
    assert str(tmp_path) not in context


@pytest.mark.anyio
async def test_resumed_distillation_keeps_learned_output_budget(tmp_path):
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            [
                {"requested_tokens": 8192, "finish_reason": "length"},
                {"requested_tokens": 16384, "finish_reason": "length"},
            ]
        ),
        encoding="utf-8",
    )
    llm = SimpleNamespace(
        model="test",
        chat=AsyncMock(
            return_value=StandardResponse(
                content=json.dumps(model_payload()),
                finish_reason="stop",
            )
        ),
    )
    card = await library.distill_one(record(), llm, audit)
    assert card["grounding"] == "exact_quote_verified"
    assert llm.chat.await_args.kwargs["max_tokens"] == 32768
    assert len(json.loads(audit.read_text(encoding="utf-8"))) == 3


@pytest.mark.anyio
async def test_invalid_quote_gets_one_correction_without_relaxing_grounding():
    wrong = model_payload()
    wrong["patterns"][0]["evidence_quote"] = "先定义目标约束再比较结果"
    llm = SimpleNamespace(
        model="test",
        chat=AsyncMock(
            side_effect=[
                StandardResponse(content=json.dumps(wrong)),
                StandardResponse(content=json.dumps(model_payload())),
            ]
        ),
    )
    result = await library.distill_one(record(), llm)
    assert result["grounding"] == "exact_quote_verified"
    assert llm.chat.await_count == 2
    llm.chat = AsyncMock(return_value=StandardResponse(content=json.dumps(wrong)))
    with pytest.raises(ValueError, match="conflicts"):
        await library.distill_one(record(), llm)
    assert llm.chat.await_count == 2


def test_export_rechecks_grounding_and_reports_pending_papers(tmp_path):
    source = tmp_path / "source"
    cards = tmp_path / "cards"
    source.mkdir()
    cards.mkdir()
    r = record()
    manifest = {
        "source_files": 2,
        "unique_papers": 2,
        "papers": [r["metadata"], {**r["metadata"], "id": "pending", "sha256": "def"}],
    }
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "example.json").write_text(json.dumps(r), encoding="utf-8")
    card = {**payload(), **r["metadata"], "grounding": "exact_quote_verified"}
    (cards / "example.json").write_text(json.dumps(card), encoding="utf-8")
    destination = tmp_path / "package" / "library.json"
    bundle = library.export_library(source, cards, destination)
    assert bundle["verified_cards"] == 1
    assert bundle["pending_ids"] == ["pending"]
    before = destination.read_bytes()
    card["patterns"][0]["evidence_quote"] = "篡改过的引文不能进入发布包"
    (cards / "example.json").write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError, match="not present"):
        library.export_library(source, cards, destination)
    assert destination.read_bytes() == before


def test_context_selects_matching_topic_within_contest(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text("通用写作方法", encoding="utf-8")
    (tmp_path / "library.json").write_text(
        json.dumps(
            {
                "cards": [
                    {"competition": "gmcm", "topic": "轴承故障诊断"},
                    {"competition": "gmcm", "topic": "山区无人机运输与航路优化"},
                    {"competition": "cumcm", "topic": "无人机定位"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(library, "LIBRARY_ROOT", tmp_path)
    text = library.context(
        "gmcm", max_cards=1, topic="山区洪涝无人机运输与中继协同优化"
    )
    assert "山区无人机运输" in text
    assert "轴承" not in text and "定位" not in text
