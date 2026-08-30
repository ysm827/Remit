#!/usr/bin/env bash
# Remit POSIX 服务启动器（macOS / Linux）：Redis + FastAPI + Vue。
#
# 用法:
#   tools/start_services.sh            后台启动三个服务，日志写入 logs/
#   tools/start_services.sh --check    只校验启动依赖，不启动任何服务
#
# 与 tools/start_services.ps1 保持同一端口契约:
#   Redis 16379 / Backend 18000 / Frontend 15173
#
# Redis 不随仓库捆绑（Windows 专用目录 tools/redis 仅含 exe），POSIX 环境按
# 仓库内置可执行文件 → PATH → Homebrew 的顺序发现本机 redis-server。

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOG_DIR="$ROOT/logs"

REDIS_PORT=16379
BACKEND_PORT=18000
FRONTEND_PORT=15173

CHECK_ONLY=0
for arg in "$@"; do
	case "$arg" in
	--check | -Check)
		CHECK_ONLY=1
		;;
	-h | --help)
		echo "用法: tools/start_services.sh [--check]"
		exit 0
		;;
	*)
		echo "[ERROR] 未知参数: $arg" >&2
		exit 1
		;;
	esac
done

die() {
	echo "[ERROR] $*" >&2
	exit 1
}

find_redis_executable() {
	local candidate
	for candidate in \
		"$ROOT/tools/redis/redis-server" \
		"$(command -v redis-server 2>/dev/null || true)" \
		/opt/homebrew/opt/redis/bin/redis-server \
		/usr/local/opt/redis/bin/redis-server \
		/opt/homebrew/bin/redis-server \
		/usr/local/bin/redis-server; do
		if [ -n "$candidate" ] && [ -x "$candidate" ]; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}

# 后端必须以 backend/ 为工作目录启动：项目内多处使用相对路径 project/work_dir。
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
if [ ! -x "$BACKEND_PYTHON" ]; then
	BACKEND_PYTHON="$BACKEND_DIR/venv/bin/python"
fi

REDIS_BIN="$(find_redis_executable || true)"
PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"

assert_dependencies() {
	if [ -z "$REDIS_BIN" ]; then
		die "未找到可用的 redis-server。请先安装 Redis: brew install redis（或把可执行文件放到 tools/redis/redis-server）"
	fi
	if [ ! -x "$BACKEND_PYTHON" ]; then
		die "后端虚拟环境不存在。请先执行: cd backend && uv sync --frozen"
	fi
	if [ ! -f "$FRONTEND_DIR/package.json" ]; then
		die "前端 package.json 不存在: $FRONTEND_DIR"
	fi
	if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
		die "前端依赖缺失。请先执行: cd frontend && pnpm install"
	fi
	if [ ! -f "$FRONTEND_DIR/node_modules/vite/bin/vite.js" ]; then
		die "Frontend Vite entry point not found. The project may have moved. Run: cd frontend; pnpm install --force --frozen-lockfile"
	fi
	if [ -z "$PNPM_BIN" ]; then
		die "未找到 pnpm。请先安装: corepack enable 或 npm install -g pnpm@10"
	fi
}

port_pids() {
	lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u
}

pid_command() {
	ps -p "$1" -o command= 2>/dev/null | head -n 1
}

pid_ppid() {
	ps -p "$1" -o ppid= 2>/dev/null | tr -d '[:space:]'
}

# 进程工作目录（lsof -Fn 输出形如 n/Users/.../Remit/frontend）。
pid_cwd() {
	lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

# 命令行或工作目录落在仓库内即视为项目进程，用于端口归属判定。
# pnpm 等包装进程的命令行指向全局安装位置，只能靠 cwd 识别。
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

# 启动器自己拉起的 redis（HOME 装在 PATH 下，命令行不含仓库路径）也算项目所有。
is_redis_process() {
	pid_command "$1" | grep -q "redis-server"
}

# $1=名称 $2=端口 $3=工作目录 其余为启动命令；端口被本项目进程占用时直接复用。
start_service() {
	local name="$1" port="$2" workdir="$3"
	shift 3
	local pids pid owned=0 redis_ok=0
	pids="$(port_pids "$port" || true)"
	if [ -n "$pids" ]; then
		for pid in $pids; do
			if is_project_process "$pid"; then
				owned=1
			fi
			if [ "$name" = "redis" ] && is_redis_process "$pid"; then
				redis_ok=1
			fi
		done
		if [ "$owned" = "1" ] || [ "$redis_ok" = "1" ]; then
			echo "[OK] $name is already listening on port $port."
			return 0
		fi
		die "Port $port is occupied by another application. Stop that application before starting Remit."
	fi

	(
		cd "$workdir" || exit 1
		exec nohup "$@" >"$LOG_DIR/$name.out.log" 2>"$LOG_DIR/$name.err.log" </dev/null
	) &
	local service_pid=$!
	printf '%s' "$service_pid" >"$LOG_DIR/$name.pid"
	echo "[STARTED] $name (PID $service_pid, port $port)"
}

wait_for_port() {
	local name="$1" port="$2" timeout="$3" waited=0
	while [ "$waited" -lt "$timeout" ]; do
		if [ -n "$(port_pids "$port")" ]; then
			echo "[READY] $name is accepting connections on port $port."
			return 0
		fi
		sleep 1
		waited=$((waited + 1))
	done
	echo "[WARN] $name 未在 ${timeout}s 内开始监听端口 $port，请查看 logs/$name.err.log"
	return 1
}

assert_dependencies

if [ "$CHECK_ONLY" = "1" ]; then
	echo "LAUNCHER_CHECK_OK"
	exit 0
fi

# 没有本地配置时先从模板生成，避免裸跑落到 Docker 专用默认值 redis://redis:6379。
if [ ! -f "$BACKEND_DIR/.env.dev" ] && [ -f "$BACKEND_DIR/.env.example" ]; then
	cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env.dev"
	echo "[INIT] 已从 .env.example 生成 backend/.env.dev，请按需填写模型 API Key。"
fi

mkdir -p "$LOG_DIR" "$LOG_DIR/redis-data"

echo "=============================================="
echo " Remit: Redis + FastAPI + Vue (macOS/Linux)"
echo " Mode: hidden background services"
echo "=============================================="

start_service redis "$REDIS_PORT" "$ROOT" \
	"$REDIS_BIN" --port "$REDIS_PORT" --bind 127.0.0.1 ::1 --dir "$LOG_DIR/redis-data"
wait_for_port redis "$REDIS_PORT" 30

start_service backend "$BACKEND_PORT" "$BACKEND_DIR" \
	"$BACKEND_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
	--ws-ping-interval 60 --ws-ping-timeout 120
wait_for_port backend "$BACKEND_PORT" 90

start_service frontend "$FRONTEND_PORT" "$FRONTEND_DIR" \
	"$PNPM_BIN" run dev --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
wait_for_port frontend "$FRONTEND_PORT" 60

echo ""
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Logs:     $LOG_DIR"
echo "Stop:     bash tools/stop_services.sh（或双击 mac_stop.command）"
