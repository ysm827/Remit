# Remit

<p align="center">
  <img src="./assets/remit-icon.png" alt="Remit 标志" width="150" />
</p>

<p align="center">
  本地优先、可检查、可恢复的数学建模工作台
</p>

<p align="center">
  <a href="https://github.com/zhou2030109-glitch/Remit/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zhou2030109-glitch/Remit/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="./README_EN.md">English</a>
</p>

Remit 把赛题理解、数据检查、模型设计、代码执行、结果验证和论文写作组织成一个带人工
确认节点的多智能体流程。项目处于 `0.1.x` 阶段，接口与工作流仍可能调整。

## 特性

- Coordinator、Modeler、Coder、Writer 四角色分阶段协作；
- OpenAI Chat/Responses、Anthropic、Gemini 等兼容接入，每个角色可独立配置；
- 任务级文件、消息、检查点和交付物管理，支持中断恢复与人工审批；
- 本地 Python/MATLAB 执行，可选 E2B 沙箱；
- 赛题 PDF 文本与插图解析、附件侦察、方法检索和开放文献检索；
- 模型评审、质量门和可追踪的论文交付流程。

想完整了解项目为什么做、一道赛题怎样从上传走到交付，可以看
[Remit 项目介绍](docs/workflow.md)；模块边界见 [架构文档](docs/architecture.md)。

## 运行要求

- Windows 10/11（桌面启动器）或支持 Docker Compose 的系统；
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)；
- Node.js 20+ 与 pnpm 10；
- 完整工作流需要 Redis。Windows 源码模式可使用仓库内置的 Redis 运行文件。

模型调用会产生第三方 API 费用。部分工作流会执行模型生成的代码，请仅在可信本机环境
运行并检查输入数据。

## 快速开始

### Windows 源码模式

```powershell
git clone https://github.com/zhou2030109-glitch/Remit.git
cd Remit

Copy-Item backend/.env.example backend/.env.dev

cd backend
uv sync --frozen

cd ../frontend
pnpm install --frozen-lockfile

cd ..
./win_start.bat
```

访问 <http://127.0.0.1:15173>。后端 API 文档位于
<http://127.0.0.1:18000/docs>。运行 `win_stop.bat` 停止服务。

### Docker Compose

```bash
cp backend/.env.example backend/.env.dev
docker compose up --build
```

前端默认端口为 `15173`，后端为 `18000`，Redis 为 `16379`。

## 模型配置

编辑本地的 `backend/.env.dev`。四个核心角色采用相同字段结构：

```dotenv
COORDINATOR_API_TYPE=openai-responses
COORDINATOR_API_KEY=your-key
COORDINATOR_MODEL=your-model
COORDINATOR_BASE_URL=https://your-provider.example/
COORDINATOR_MAX_TOKENS=8192
```

把 `COORDINATOR` 替换为 `MODELER`、`CODER`、`WRITER` 即可分别配置。完整字段见
[配置文档](docs/configuration.md)。不要提交任何 `.env` 文件或真实密钥。

## 合成示例

仓库只附带项目自写的社区降温合成数据，不包含第三方比赛题面或附件。可通过
`POST /example` 并传入 `{"example_id": "urban-cooling"}` 创建演示任务，也可以直接在
界面上传自己的题目和数据。

## 开发与验证

```powershell
cd backend
uv run ruff check app tests
uv run pytest tests -q

cd ../frontend
pnpm run lint
pnpm run build

cd ..
backend/.venv/Scripts/python.exe -m pytest tests -q
```

Windows 安装包可通过以下命令生成，默认产物位于当前用户本地应用数据目录下的
`Remit/build/output/RemitSetup.exe`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/package_win.ps1
```

## 项目结构

```text
backend/      FastAPI、工作流、Agent、模型接入与执行器
frontend/     Vue 3 + TypeScript 工作台
tools/        Windows 启动、打包工具与 Redis 运行文件
assets/       Remit 品牌资源
docs/         架构、配置与来源审计文档
tests/        仓库级启动器和配置契约测试
```

任务数据写入 `backend/project/work_dir/<task-id>/`，日志写入 `logs/`，两者均不应提交。

## 安全边界

Remit 面向可信的单用户本机环境，不具备公网多租户服务所需的认证、授权和执行隔离。
公开部署前必须补充安全边界。漏洞请按 [安全策略](SECURITY.md) 私下报告。

## 参与和许可证

欢迎提交 Issue 与 Pull Request。开始前请阅读 [贡献指南](CONTRIBUTING.md) 和
[社区行为准则](CODE_OF_CONDUCT.md)。Remit 自有源码与合成示例采用
[MIT License](LICENSE)；依赖和捆绑运行文件保留各自许可证，详见
[第三方声明](THIRD_PARTY_NOTICES.md)。

当前源码经过针对 MathModelAgent 的来源审计和独立实现整改；早期公开版本的来源事实不
因分支历史重建而改变。技术范围、残余分类和限制见 [NOTICE.md](NOTICE.md) 与
[来源审计](docs/originality-audit.md)。这些材料用于透明披露，不构成法律结论。

## 加入交流群

想交流 Remit 的使用、数学建模工作流或一起参与开发，可以扫码加入微信群
**Remit（数模 agent）**。欢迎分享建议、问题和实际使用体验。

<p align="center">
  <img src="./assets/remit-wechat-group.png" alt="Remit 数模 Agent 微信交流群二维码" width="360" />
</p>

> 微信群二维码有效期较短，当前图片标注为 9 月 4 日前有效；过期后会在仓库更新。
