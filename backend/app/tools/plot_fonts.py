"""Shared, idempotent Matplotlib setup for local and cloud kernels."""

from pathlib import Path

# 内核需要独立执行这段代码；将源码作为常量保留，兼容仅字节码安装包。
# 独立命名空间避免用户代码改写闭包所依赖的全局变量。
_KERNEL_SOURCE = r"""
from functools import lru_cache
from pathlib import Path
from matplotlib import font_manager, ft2font, rcParams
from matplotlib.figure import Figure
from matplotlib.text import Text


def install(work_dir, bundled_fonts):
    preferred = ["FandolHei", "Microsoft YaHei", "SimHei", "PingFang SC",
                 "Heiti SC", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei"]
    known = {str(Path(f.fname).resolve()) for f in font_manager.fontManager.ttflist}
    for font in [*map(Path, bundled_fonts), *Path(work_dir).glob("*")]:
        path = str(font.resolve())
        if font.is_file() and font.suffix.lower() in {".ttf", ".otf", ".ttc"} and path not in known:
            font_manager.fontManager.addfont(path)
            known.add(path)
    rcParams.update({"font.family": "sans-serif", "font.sans-serif": preferred + ["DejaVu Sans"],
                     "axes.unicode_minus": False})
    available = sorted(font_manager.fontManager.ttflist,
                       key=lambda f: preferred.index(f.name) if f.name in preferred else len(preferred))
    state = getattr(Text._get_layout, "_remit_font_guard", None)
    if state is not None:
        # 新任务目录可能提供了额外字体；保留同一补丁，刷新覆盖查询。
        state["available"] = available
        state["clear"]()
        return
    state = {"available": available}

    @lru_cache(maxsize=128)
    def charset(path):
        return set(ft2font.FT2Font(path).get_charmap())

    @lru_cache(maxsize=1024)
    def covering_font(characters):
        for font in state["available"]:
            try:
                if set(characters) <= charset(font.fname):
                    return font.fname
            except (OSError, RuntimeError):
                continue
        raise RuntimeError("绘图缺少能显示这些中文字符的字体，请安装/随包提供 Noto Sans CJK 字体后重新导出图片；不能交付方框文字的图表。")

    state["clear"] = covering_font.cache_clear
    layout = Text._get_layout

    def guarded_layout(self, renderer):
        characters = tuple(sorted({ord(c) for c in self.get_text() if '\u3400' <= c <= '\u9fff'}))
        if characters:
            prop = self.get_fontproperties().copy()
            existing = font_manager.findfont(prop)
            if not set(characters) <= charset(existing):
                prop.set_file(covering_font(characters))
                self.set_fontproperties(prop)
        return layout(self, renderer)

    guarded_layout._remit_font_guard = state
    Text._get_layout = guarded_layout

    # 中文字体经常缺少上标字形，沿用 mathtext 转换；闭包只安装一次。
    superscripts = {'¹': '$^1$', '²': '$^2$', '³': '$^3$', '⁴': '$^4$', '⁻': '$^-$', 'µ': r'$\mu$'}
    savefig = Figure.savefig

    def guarded_savefig(self, *args, **kwargs):
        for text in self.findobj(match=Text):
            original = text.get_text()
            if '$' not in original:
                normalized = ''.join(superscripts.get(c, c) for c in original)
                if normalized != original:
                    text.set_text(normalized)
        return savefig(self, *args, **kwargs)

    Figure.savefig = guarded_savefig


install(_work_dir, _bundled_fonts)
"""


def bootstrap(work_dir: str) -> str:
    """Return self-contained initialization code for an isolated Python kernel."""
    bundled = [
        str(p)
        for p in (Path(__file__).resolve().parents[2] / "fonts").glob("*")
        if p.suffix.lower() in {".ttf", ".otf", ".ttc"}
    ]
    namespace = {"_work_dir": work_dir, "_bundled_fonts": bundled}
    return f"exec({_KERNEL_SOURCE!r}, {namespace!r})"


def install_plot_font_guard(work_dir: str | Path) -> None:
    """Apply the same font guard directly in the current Python process."""
    exec(bootstrap(str(work_dir)), {})
