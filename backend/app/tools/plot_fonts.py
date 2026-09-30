"""Matplotlib render-time font coverage, including after seaborn resets styles.

This module is also injected into isolated kernels; keep it self-contained.
"""

from pathlib import Path


def install_plot_font_guard(work_dir="."):
    from functools import lru_cache
    from matplotlib import font_manager, ft2font, rcParams
    from matplotlib.text import Text

    for font in Path(work_dir).glob("*"):
        if font.suffix.lower() in {".ttf", ".otf", ".ttc"}:
            font_manager.fontManager.addfont(str(font))
    preferred = ["FandolHei", "Microsoft YaHei", "SimHei", "PingFang SC", "Heiti SC", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei"]
    available = sorted(font_manager.fontManager.ttflist, key=lambda f: preferred.index(f.name) if f.name in preferred else len(preferred))
    rcParams.update({"font.family": "sans-serif", "font.sans-serif": preferred + ["DejaVu Sans"], "axes.unicode_minus": False})
    if getattr(Text._get_layout, "_remit_font_guard", False):
        return

    @lru_cache(maxsize=128)
    def charset(path):
        return set(ft2font.FT2Font(path).get_charmap())

    @lru_cache(maxsize=1024)
    def covering_font(characters):
        for font in available:
            try:
                if set(characters) <= charset(font.fname):
                    return font.fname
            except (OSError, RuntimeError):
                continue
        raise RuntimeError("绘图缺少能显示这些中文字符的字体，请安装/随包提供 Noto Sans CJK 字体后重新导出图片；不能交付方框文字的图表。")

    layout = Text._get_layout

    def guarded_layout(self, renderer):
        text = self.get_text()
        characters = tuple(sorted({ord(c) for c in text if '\u3400' <= c <= '\u9fff'}))
        if characters:
            prop = self.get_fontproperties().copy()
            existing = font_manager.findfont(prop)
            if not set(characters) <= charset(existing):
                # Resolve against actual glyph coverage, not a guessed font name.
                prop.set_file(covering_font(characters))
                self.set_fontproperties(prop)
        return layout(self, renderer)

    guarded_layout._remit_font_guard = True
    Text._get_layout = guarded_layout


def bootstrap(work_dir: str) -> str:
    """Run the same coverage guard in local and cloud kernels."""
    source = Path(__file__).read_text(encoding="utf-8")
    bundled = [str(p) for p in (Path(__file__).resolve().parents[2] / "fonts").glob("*") if p.suffix.lower() in {".ttf", ".otf", ".ttc"}]
    return ("exec(" + repr(source) + ")\nfrom matplotlib import font_manager\n"
            + "for _font in " + repr(bundled) + ":\n    if Path(_font).is_file(): font_manager.fontManager.addfont(_font)\n"
            + "install_plot_font_guard(" + repr(work_dir) + ")")
