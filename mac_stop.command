#!/bin/bash
# Remit macOS 双击停止入口（对应 Windows 的 win_stop.bat）。
cd "$(dirname "$0")" || exit 1

bash tools/stop_services.sh
code=$?
if [ "$code" -ne 0 ]; then
	echo ""
	echo "[ERROR] 部分服务未能停止，请查看上方提示。"
	read -n 1 -s -r -p "按任意键关闭窗口..."
else
	echo ""
	echo "服务已停止，可以直接关闭本窗口。"
fi
exit "$code"
