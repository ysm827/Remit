"""独立进程内运行固定科学夹具；stdout 仅包含允许清单检查结果。"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def check(directory: Path) -> list[dict]:
    """验证实际 Jupyter 内核、依赖、中文图和最小中文 PDF。"""
    directory = directory.resolve()
    checks = []
    manager = None
    try:
        from jupyter_client import KernelManager

        manager = KernelManager()
        # 明确使用当前运行时，避免开发机的全局 kernelspec 掩盖缺失依赖。
        manager.kernel_spec.argv = [
            sys.executable,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        manager.start_kernel(
            cwd=str(directory), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        client = manager.blocking_client()
        client.start_channels()
        client.wait_for_ready(timeout=25)
        # 使用真实任务的初始化代码，覆盖字体补丁等实际执行路径。
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.tools.local_interpreter import LocalCodeInterpreter
        from app.tools.notebook_serializer import NotebookSerializer

        interpreter = LocalCodeInterpreter(
            "local-environment-check",
            str(directory),
            NotebookSerializer(str(directory)),
        )
        interpreter.km, interpreter.kc = manager, client
        interpreter._pre_execute_code()
        font = Path(__file__).resolve().parents[2] / "fonts" / "simhei.ttf"
        code = f"""
import json
import numpy as np
import pandas as pd
import scipy, sklearn
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
font = {str(font)!r}
font_manager.fontManager.addfont(font)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
x = np.arange(6, dtype=float)
y = 2 * x + 1
fit = np.polyfit(x, y, 1)
predicted = np.polyval(fit, x)
pd.DataFrame({{"x": x, "actual": y, "predicted": predicted}}).to_csv("result.csv", index=False)
plt.plot(x, y, label="观测值")
plt.xlabel("时间（秒）")
plt.ylabel("距离（米）")
plt.legend()
plt.savefig("check.png")
plt.close("all")
"""
        reply = client.execute_interactive(
            code, timeout=35, output_hook=lambda msg: None
        )
        if reply["content"]["status"] != "ok":
            raise RuntimeError("kernel_check_failed")
        # 检查器从文件独立复算，不能接受被执行程序自己声明 pass。
        import csv

        with (directory / "result.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 6
        mse = (
            sum(
                (float(row["predicted"]) - (2 * float(row["x"]) + 1)) ** 2
                for row in rows
            )
            / 6
        )
        assert mse < 1e-20 and (directory / "check.png").stat().st_size > 1000
        checks.append(
            {
                "id": "python",
                "label": "Python 内核、科学计算与中文图",
                "required": True,
                "status": "passed",
                "detail": "固定线性数据：6 行结果，独立复算误差 < 1e-20。",
            }
        )
    except Exception as exc:
        checks.append(
            {
                "id": "python",
                "label": "Python 内核、科学计算与中文图",
                "required": True,
                "status": "failed",
                "detail": f"本地检查未通过（{type(exc).__name__}），请检查内核、科学计算依赖与中文字体。",
            }
        )
    finally:
        if manager is not None and manager.has_kernel:
            manager.shutdown_kernel(now=True)
        if "client" in locals():
            client.stop_channels()
    tex = shutil.which("xelatex")
    if not tex:
        checks.append(
            {
                "id": "tex",
                "label": "中文论文 PDF 编译",
                "required": False,
                "status": "missing",
                "detail": "找不到 XeLaTeX；可保存源码，当前不能生成 PDF。",
            }
        )
    else:
        source = directory / "check.tex"
        source.write_text(
            r"\documentclass[UTF8,fontset=fandol]{ctexart}\begin{document}环境检查：中文论文。\end{document}",
            encoding="utf-8",
        )
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from app.utils.tex_process import run_xelatex

            result = run_xelatex(
                [
                    tex,
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "check.tex",
                ],
                pdf_path=directory / "check.pdf",
                cwd=directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=25,
            )
            passed = result.returncode == 0 and (directory / "check.pdf").is_file()
        except (OSError, subprocess.TimeoutExpired):
            passed = False
        checks.append(
            {
                "id": "tex",
                "label": "中文论文 PDF 编译",
                "required": False,
                "status": "passed" if passed else "failed",
                "detail": "" if passed else "工具存在，但中文最小论文编译未通过。",
            }
        )
    return checks


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1])), ensure_ascii=True))
