# 可靠性与安全边界回归

本轮修复覆盖人工返修、自动模式 Pilot、项目切换、断线补偿、取消、文件接口、上传、
Markdown 渲染、Windows 启停和镜像构建边界。升级保持原有 REST 路径和消息类型，
新增事件序号及可选生命周期字段，并兼容旧任务消息档案。

## 行为保证

| 场景 | 保证 | 回归位置 |
| --- | --- | --- |
| 人工返修与恢复 | 返修重新计算；本轮计算完成后写作中断，恢复时不重复计算 | `backend/tests/test_workflow_revision_execution.py` |
| 自动模式选型 | 正式求解采用 Pilot 保存的新方案；探索降级时沿用原方案 | 同上 |
| 模型请求取消 | 取消、超时和重复停止等待 Provider 子任务释放资源 | `backend/tests/test_agent_cancellation.py` |
| 消息持久化 | 旧 JSON 一次迁移、并发追加不丢失、序号分页、删除不复活 | `backend/tests/test_message_archive.py` |
| 断线/漏播 | Redis 历史审批重放、实时消息和持久化漏播补偿 | `backend/tests/test_message_delivery.py` |
| 文件上传 | 目录越界拒绝、同名文件拒绝、整批大小校验及分块写入 | `backend/tests/test_file_boundaries.py` |
| 接收与调度 | 入队失败清理新目录，Redis 故障仍可取消，排队任务禁止删除 | `backend/tests/test_intake_lifecycle.py` |
| 页面状态 | 项目切换、迟到响应、重连审批、旧进度与 CSV 预览隔离 | `frontend/tests/` |
| HTML 渲染 | 最终 HTML 净化，保留 KaTeX/MathML 的安全渲染 | `frontend/tests/` |
| Windows 进程 | PID 与启动时间/路径匹配才停止，不追溯终止用户终端 | `tests/test_win_stop_launcher.py` |
| 桌面与安装 | 启停互斥、安装版单实例、安装检查失败返回非零 | `backend/tests/test_desktop_launcher.py`、`test_prod_launcher.py` |

## 本地验证

后端运行 `uv run pytest tests -q`、`uv run ruff check app tests`。
前端运行 `pnpm install --frozen-lockfile`、`pnpm test`、`pnpm lint`、`pnpm build`。
仓库根目录使用后端虚拟环境运行 `python -m pytest tests -q`。

单元测试隔离本机消息档案和 Redis。真实 Redis 测试使用随机本地端口及临时目录，
只启动和停止其自身子进程；没有 Redis 运行文件的平台会明确跳过该集成测试。
模型与桌面进程的回归采用替身，不能替代真实模型预算验收或 Windows 安装包验收。

Docker 使用允许清单控制构建上下文，并显式复制 `app/` 和依赖清单；真实配置、
工作目录及日志不进入镜像。源代码测试通过不等同于镜像或安装程序已实构建。
