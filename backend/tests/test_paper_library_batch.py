"""Publishing a successful or resumed batch must update the bundled library."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_success_and_fully_cached_batch_both_publish(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "tools/distill_paper_library.py"
    spec = importlib.util.spec_from_file_location("distill_batch_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, output = tmp_path / "source", tmp_path / "cards"
    source.mkdir()
    metadata = {"id": "example", "sha256": "abc"}
    (source / "manifest.json").write_text(json.dumps({"papers": [metadata]}))
    (source / "example.json").write_text(json.dumps({"metadata": metadata}))
    card = {**metadata, "grounding": "exact_quote_verified", "patterns": [{}, {}]}
    distill = AsyncMock(return_value=card)
    export = Mock()
    monkeypatch.setattr(module, "distill_one", distill)
    monkeypatch.setattr(module, "export_library", export)
    monkeypatch.setattr(module, "LLMFactory", Mock())
    bundle = tmp_path / "library.json"
    await module.run(source, output, 1, bundle)
    assert json.loads((output / "example.json").read_text()) == card
    assert export.call_count == 2
    assert not (output / ".distilling.lock").exists()
    assert not list(output.glob("*.tmp"))
    export.reset_mock()
    await module.run(source, output, 1, bundle)
    distill.assert_awaited_once()
    export.assert_called_once_with(source, output, bundle)
