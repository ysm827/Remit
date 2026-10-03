from pathlib import Path

from app.utils.paper_polish import (
    _merge_symbol_section_tables,
    _normalize_figures,
    _normalize_numeric_tables,
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


def test_normalize_unicode_greek_wraps_text_mode_letters() -> None:
    assert (
        _normalize_unicode_greek("并用ε-约束")
        == "并用`\\(\\varepsilon\\)`{=latex}-约束"
    )
    assert (
        _normalize_unicode_greek("$\\alpha$ 与 ρ")
        == "$\\alpha$ 与 `\\(\\rho\\)`{=latex}"
    )
    assert _normalize_unicode_greek("无希腊字母") == "无希腊字母"
    assert (
        _normalize_unicode_greek("体积 0.25 m³") == "体积 0.25 m`\\({}^{3}\\)`{=latex}"
    )


def test_unicode_minus_before_digit_cannot_swallow_chinese_prose(tmp_path):
    from app.utils.paper_polish import _markdown_fragment_to_latex

    result = _markdown_fragment_to_latex("秩相关为 −1，说明边界稳定，$k=2$。", tmp_path)
    assert r"\(-\)1，说明边界稳定" in result
    assert r"\(k=2\)" in result
    assert r"\$" not in result


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
    assert "width=0.68\\linewidth" in out
    assert "\\begin{figure}[htb]" in out
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


def test_figures_attach_detached_title_preserve_math_and_prose():
    figure = (
        "\\begin{figure}\n\\includegraphics{x.png}\n\\caption{x.png}\n\\end{figure}\n"
    )
    result = _normalize_figures(
        "\\section{六、分析}\n"
        + figure
        + "\n图 6-6(a)　需求 $x_{i}$ 变化\n\n图 6-6 给出结果。\n"
    )
    assert result.count("需求") == 1
    assert r"\caption*{图 6-6(a)　需求 $x_{i}$ 变化}" in result
    assert "图 6-6 给出结果。" in result
    prose = _normalize_figures(figure + "\n图 6-6 给出各档位计算结果\n\n")
    assert r"\caption*{图 1}" in prose
    assert "图 6-6 给出各档位计算结果" in prose


def test_numeric_table_keeps_values_and_attaches_title():
    data = r"0.10 & 44.5625 & 33876.7 & 是 \\" + "\n"
    table = (
        "表 6-1　扰动响应\n\n{\\def\\LTcaptype{none}\n"
        "\\begin{longtable}[]{@{}rrrr@{}}\n\\toprule\\noalign{}\n"
        r"$\rho$ & 平均 $q_{max}$/kg & 作业时间/s & 可行 \\" + "\n"
        "\\midrule\\noalign{}\n\\endhead\n\\bottomrule\\noalign{}\n\\endlastfoot\n"
        + data
        + "\\end{longtable}\n}\n"
    )
    result = _normalize_numeric_tables(table)
    assert data in result
    assert "作业时间/s" in result
    assert "shortstack" not in result
    assert r"@{\extracolsep{\fill}}cccc" in result
    assert "平均 $q_{max}$/kg" in result
    assert result.count("扰动响应") == 1
    assert r"\caption*{表 6-1　扰动响应}" in result
    assert r"\begin{table}[!htbp]" in result
    # A multipage table must not be forced into a giant float.
    assert "longtable" in _normalize_numeric_tables(table.replace(data, data * 30))


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
    assert "\\begin{table}[!htbp]" in merged
    assert "\\caption{主要符号说明}" in merged
    assert "\\subsubsection" not in merged
    assert "\\(x\\)" in merged and "\\(E\\)" in merged
    assert "p{0.25\\linewidth}" in merged
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
