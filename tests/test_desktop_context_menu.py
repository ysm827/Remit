"""Verify native menu configuration stays on the UI thread and keeps debug off."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


def test_context_menu_enables_editing_without_debug():
    path = Path(__file__).resolve().parents[1] / "tools/desktop_app.py"
    spec = importlib.util.spec_from_file_location("remit_desktop_menu_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = SimpleNamespace(
        AreDefaultContextMenusEnabled=False, AreDevToolsEnabled=False
    )
    native = SimpleNamespace(
        browser=SimpleNamespace(
            webview=SimpleNamespace(CoreWebView2=SimpleNamespace(Settings=settings))
        ),
        Invoke=Mock(side_effect=lambda callback: callback()),
    )
    # Use the shell method without starting the app, tray, or service lifecycle.
    owner = SimpleNamespace(
        window=SimpleNamespace(native=native),
        shutdown_event=SimpleNamespace(is_set=lambda: False),
    )
    method = next(
        value._enable_context_menu
        for value in vars(module).values()
        if isinstance(value, type) and hasattr(value, "_enable_context_menu")
    )
    with patch.dict(
        "sys.modules", {"System": SimpleNamespace(Action=lambda callback: callback)}
    ):
        method(owner)
    native.Invoke.assert_called_once()
    assert settings.AreDefaultContextMenusEnabled is True
    assert settings.AreDevToolsEnabled is False
