#!/usr/bin/env bash
# Remit POSIX 服务停止器（macOS / Linux）。与 tools/stop_services.ps1 保持
# 相同语义：优先按 logs/<name>.pid 记录停止；PID 文件缺失时按端口发现监听
# 进程，并只停止属于本项目的进程链，外部进程仅告警不误杀。

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"

REDIS_PORT=16379
BACKEND_PORT=18000
FRONTEND_PORT=15173

# macOS 自带 BSD tail 用 -r 反转行序，GNU coreutils 环境回退到 tac。
if tail -r </dev/null >/dev/null 2>&1; then
	REVERSER="tail -r"
else
	REVERSER="tac"
fi

port_pids() {
	lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u
}

pid_command() {
	ps -p "$1" -o command= 2>/dev/null | head -n 1
}

pid_ppid() {
	ps -p "$1" -o ppid= 2>/dev/null | tr -d '[:space:]'
}

pid_alive() {
	ps -p "$1" >/dev/null 2>&1
}

# 进程工作目录（lsof -Fn 输出形如 n/Users/.../Remit/frontend）。
pid_cwd() {
	lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

# 命令行或工作目录落在仓库内即视为项目进程。pnpm 等包装进程的命令行
# 指向全局安装位置（如 /usr/local/bin/pnpm），只能靠 cwd 识别。
is_project_process() {
	local pid="$1" depth=0 cmd parent cwd
	while [ -n "$pid" ] && [ "$pid" != "0" ] && [ "$pid" != "1" ] && [ "$depth" -lt 8 ]; do
		cmd="$(pid_command "$pid")"
		[ -n "$cmd" ] || return 1
		case "$cmd" in
		*"$ROOT"*) return 0 ;;
		esac
		cwd="$(pid_cwd "$pid")"
		case "$cwd" in
		"$ROOT" | "$ROOT"/*) return 0 ;;
		esac
		parent="$(pid_ppid "$pid")"
		if [ -z "$parent" ] || [ "$parent" = "$pid" ]; then
			return 1
		fi
		pid="$parent"
		depth=$((depth + 1))
	done
	return 1
}

is_redis_process() {
	pid_command "$1" | grep -q "redis-server"
}

# 输出该 PID 及其全部后代（父在前），供自底向上终止。
collect_tree() {
	local pid="$1" child
	echo "$pid"
	for child in $(pgrep -P "$pid" 2>/dev/null); do
		collect_tree "$child"
	done
}

# $1=PID $2=服务名: 先整组 TERM，宽限 5 秒后对残留进程 KILL。
kill_tree() {
	local pid="$1" name="$2" list p
	list="$(collect_tree "$pid" | $REVERSER)"
	[ -n "$list" ] || return 0
	for p in $list; do
		kill -TERM "$p" 2>/dev/null || true
	done
	local waited=0
	while [ "$waited" -lt 50 ]; do
		pid_alive "$pid" || break
		sleep 0.1
		waited=$((waited + 1))
	done
	for p in $list; do
		kill -KILL "$p" 2>/dev/null || true
	done
	echo "[STOPPED] $name (PID $pid)"
}

# 沿父链找到最上层属于本项目的祖先，从那里整棵终止，避免遗留包装进程。
topmost_project_ancestor() {
	local pid="$1" parent cmd
	while :; do
		parent="$(pid_ppid "$pid")"
		if [ -z "$parent" ] || [ "$parent" = "0" ] || [ "$parent" = "1" ] || [ "$parent" = "$pid" ]; then
			break
		fi
		cmd="$(pid_command "$parent")"
		[ -n "$cmd" ] || break
		case "$cmd" in
		*"$ROOT"*) pid="$parent" ;;
		*) break ;;
		esac
	done
	echo "$pid"
}

service_port() {
	case "$1" in
	frontend) echo "$FRONTEND_PORT" ;;
	backend) echo "$BACKEND_PORT" ;;
	redis) echo "$REDIS_PORT" ;;
	esac
}

for service in frontend backend redis; do
	port="$(service_port "$service")"
	pid_file="$LOG_DIR/$service.pid"

	if [ -f "$pid_file" ]; then
		pid="$(tr -d '[:space:]' <"$pid_file")"
		rm -f "$pid_file"
		if [ -z "$pid" ] || ! pid_alive "$pid"; then
			echo "[OK] $service is already stopped."
			continue
		fi
		# PID 可能已被系统回收复用：确认仍属于本项目才按 PID 终止；
		# 无法确认时继续落到按端口发现，避免误杀也避免漏杀。
		cmd="$(pid_command "$pid")"
		if [ "$service" = "redis" ] && is_redis_process "$pid"; then
			kill_tree "$pid" "$service"
			continue
		elif [ -n "$cmd" ] && is_project_process "$pid"; then
			kill_tree "$pid" "$service"
			continue
		fi
	fi

	pids="$(port_pids "$port" || true)"
	if [ -z "$pids" ]; then
		echo "[OK] $service is already stopped."
		continue
	fi

	stopped=0
	foreign=0
	for pid in $pids; do
		if [ "$service" = "redis" ] && is_redis_process "$pid"; then
			:
		elif ! is_project_process "$pid"; then
			foreign=1
			continue
		fi
		top="$(topmost_project_ancestor "$pid")"
		kill_tree "$top" "$service"
		stopped=1
	done

	if [ "$stopped" = "0" ]; then
		echo "[WARN] $service uses port $port, but it was not started from this project; leaving it running."
	fi
done
