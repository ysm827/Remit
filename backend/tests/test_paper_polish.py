from pathlib import Path
import re

from app.utils.paper_polish import (
    _merge_symbol_section_tables,
    _markdown_fragment_to_latex,
    _normalize_figures,
    _normalize_keywords,
    _normalize_unicode_greek,
    enforce_em_dash_budget,
    polish_markdown,
)


def test_enforce_em_dash_budget_normalizes_excess() -> None:
    assert enforce_em_dash_budget("甲—乙—丙—丁") == "甲—乙—丙，丁"


def test_polish_markdown_applies_em_dash_budget(tmp_path: Path) -> None:
    polished = polish_markdown("# 标题\n\n甲—乙—丙—丁", tmp_path)
    assert polished.count("—") == 2
    assert "丙，丁" in polished


def test_normalize_unicode_greek_wraps_text_mode_letters(tmp_path) -> None:
    # 验证送入 TeX 的实际内容；Pandoc 原始片段是内部表示，不要求特定 Markdown 分隔符。
    fragment = _markdown_fragment_to_latex(
        "并用ε-约束，ε2、$\\alpha$ 与 ρ，体积 0.25 m³，范围 x∈[0,5]", tmp_path
    )
    assert fragment.count(r"\varepsilon") == 2
    assert r"\(\varepsilon\)2" in fragment
    assert r"\alpha" in fragment and r"\rho" in fragment
    assert r"{}^{3}" in fragment
    assert r"\(\in\)" in fragment and "∈" not in fragment
    assert "0.25" in fragment and "{=latex}" not in fragment
    assert _normalize_unicode_greek("无希腊字母") == "无希腊字母"
    once = _normalize_unicode_greek("并用ε-约束")
    assert _normalize_unicode_greek(once) == once


def test_normalize_figures_uniform_width_and_caption() -> None:
    body = (
        "\\section{五、模型的建立与求解}\n"
        "正文引用图 5-1。\n"
        "\\begin{figure}\n\\centering\n"
        "\\pandocbounded{\\includegraphics[keepaspectratio,alt={收敛曲线}]{assets/x.png}}\n"
        "\\caption{收敛曲线}\n\\end{figure}\n"
        "后续段落。\n"
        "\\begin{figure}\n\\centering\n"
        "\\pandocbounded{\\includegraphics[keepaspectratio]{assets/y.png}}\n"
        "\\caption{图 9-9 敏感性分析}\n\\end{figure}\n"
    )
    out = _normalize_figures(body)
    widths = re.findall(r"width=([\d.]+)\\linewidth", out)
    assert len(widths) == 2 and len(set(widths)) == 1
    assert 0.5 <= float(widths[0]) <= 1
    assert "keepaspectratio" in out
    assert "\\caption*{图 5-1　收敛曲线}" in out
    assert "\\caption*{图 9-9　敏感性分析}" in out
    assert "alt=" not in out


def test_normalize_keywords_uses_dunhao() -> None:
    assert (
        _normalize_keywords("集合划分  列生成  局部搜索")
        == "集合划分、列生成、局部搜索"
    )
    assert (
        _normalize_keywords("集合划分, 列生成;局部搜索") == "集合划分、列生成、局部搜索"
    )


def test_merge_symbol_section_tables_merges_split_tables() -> None:
    body = (
        "\\subsection{4.1 符号说明}\n\n引言。\n\n"
        "\\subsubsection{4.1.1 集合}\n\n"
        "{\\def\\LTcaptype{none} % do not increment counter\n"
        "\\begin{longtable}[]{@{}lll@{}}\n"
        "\\toprule\\noalign{}\n符号 & 含义 & 单位 \\\\\n\\midrule\\noalign{}\n\\endhead\n"
        "\\bottomrule\\noalign{}\n\\endlastfoot\n"
        "\\(x\\) & 位置 & m \\\\\n"
        "\\end{longtable}\n}\n\n"
        "\\subsubsection{4.1.2 能耗}\n\n"
        "{\\def\\LTcaptype{none} % do not increment counter\n"
        "\\begin{longtable}[]{@{}lll@{}}\n"
        "\\toprule\\noalign{}\n符号 & 含义 & 单位 \\\\\n\\midrule\\noalign{}\n\\endhead\n"
        "\\bottomrule\\noalign{}\n\\endlastfoot\n"
        "\\(E\\) & 能耗 & kWh \\\\\n"
        "\\end{longtable}\n}\n\n"
        "\\subsection{4.2 数据预处理}\n"
    )
    merged = _merge_symbol_section_tables(body)
    assert merged.count("\\begin{tabular}") == 1
    assert "\\centering" in merged
    assert "\\caption{主要符号说明}" in merged
    assert "\\subsubsection" not in merged
    assert "\\(x\\)" in merged and "\\(E\\)" in merged
    assert r"\toprule" in merged and r"\midrule" in merged and r"\bottomrule" in merged
    assert "\\subsection{4.2 数据预处理}" in merged


def test_merge_symbol_section_tables_handles_pandoc_fullwidth_spec() -> None:
    body = (
        "\\subsection{4.1 符号说明}\n\n"
        "\\subsubsection{4.1.1 集合}\n\n"
        "{\\def\\LTcaptype{none} % do not increment counter\n"
        "\\begin{longtable}[]{@{}\n"
        "  >{\\raggedright\\arraybackslash}p{(\\linewidth - 4\\tabcolsep) * \\real{0.3333}}\n"
        "  >{\\raggedright\\arraybackslash}p{(\\linewidth - 4\\tabcolsep) * \\real{0.3333}}\n"
        "  >{\\raggedright\\arraybackslash}p{(\\linewidth - 4\\tabcolsep) * \\real{0.3333}}@{}}\n"
        "\\toprule\\noalign{}\n"
        "\\begin{minipage}[b]{\\linewidth}\\raggedright\n符号\n\\end{minipage} & "
        "\\begin{minipage}[b]{\\linewidth}\\raggedright\n含义\n\\end{minipage} & "
        "\\begin{minipage}[b]{\\linewidth}\\raggedright\n单位\n\\end{minipage} \\\\\n"
        "\\midrule\\noalign{}\n\\endhead\n"
        "\\bottomrule\\noalign{}\n\\endlastfoot\n"
        "\\(x\\) & 位置 & m \\\\\n"
        "\\end{longtable}\n}\n\n"
        "\\subsubsection{4.1.2 能耗}\n\n"
        "{\\def\\LTcaptype{none} % do not increment counter\n"
        "\\begin{longtable}[]{@{}lll@{}}\n"
        "\\toprule\\noalign{}\n符号 & 含义 & 单位 \\\\\n\\midrule\\noalign{}\n\\endhead\n"
        "\\bottomrule\\noalign{}\n\\endlastfoot\n"
        "\\(E\\) & 能耗 & kWh \\\\\n"
        "\\end{longtable}\n}\n"
    )
    merged = _merge_symbol_section_tables(body)
    assert merged.count("\\begin{tabular}") == 1
    assert "\\begin{minipage}" not in merged
    assert "\\(x\\)" in merged and "\\(E\\)" in merged
