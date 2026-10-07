"""Caption styling is cosmetic and must run on the native UI thread."""

import ctypes
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


@pytest.mark.parametrize("result", [0, -2147024809])
def test_caption_colors_on_ui_thread_and_unsupported_windows_is_safe(result):
    path = Path(__file__).resolve().parents[1] / "tools/desktop_app.py"
    spec = importlib.util.spec_from_file_location("remit_frame_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    setter = Mock(return_value=result)
    marker = Mock(return_value=True)
    native = SimpleNamespace(
        Text="Remit 数学建模工作台",
        ShowIcon=True,
        Handle=SimpleNamespace(ToInt64=lambda: 123),
        Invoke=Mock(side_effect=lambda callback: callback()),
    )
    owner = SimpleNamespace(
        window=SimpleNamespace(native=native),
        shutdown_event=SimpleNamespace(is_set=lambda: False),
    )
    with patch.dict("sys.modules", {"System": SimpleNamespace(Action=lambda f: f)}), patch.object(
        ctypes, "windll", SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=setter), user32=SimpleNamespace(SetPropW=marker)), create=True
    ):
        module.DesktopApp._style_window_frame(owner)
    native.Invoke.assert_called_once()
    assert native.Text == ""
    assert native.ShowIcon is False
    marker.assert_called_once()
    assert setter.call_count == 2
    assert [call.args[1] for call in setter.call_args_list] == [35, 36]
    assert [call.args[2]._obj.value for call in setter.call_args_list] == [0xF7F7F7, 0x626262]


def test_blank_caption_window_is_found_by_identity():
    path = Path(__file__).resolve().parents[1] / "tools/desktop_app.py"
    spec = importlib.util.spec_from_file_location("remit_identity_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    user32 = SimpleNamespace(
        GetPropW=Mock(return_value=1),
        GetWindowTextLengthW=Mock(),
        EnumWindows=Mock(side_effect=lambda callback, arg: callback(123, arg)),
        ShowWindow=Mock(), SetForegroundWindow=Mock(),
    )
    with patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
        module._activate_existing_window()
    user32.GetWindowTextLengthW.assert_not_called()
    user32.ShowWindow.assert_called_once_with(123, 9)
    user32.SetForegroundWindow.assert_called_once_with(123)
