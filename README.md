# Remit Agent

本地数学建模工作台：通过团队对话，让协调手、建模手、代码手和论文手协作完成题目分析、计算与论文写作。

[English](README_EN.md) · [安装与分发](docs/distribution.md) · [配置说明](docs/configuration.md) · [赛事适配](docs/competition-adapters.md)

## 当前状态

这是持续开发中的源码版本。支持计划确认、附件与文件夹导入、分步执行、断点恢复、成果审核、LaTeX 编辑与 PDF 导出。探索实验按小问执行并保留已校验的中间结果。

模型可能生成错误代码，接口也可能超时；需要检查实际计算结果并完成用户验收。软件测试通过不代表某道赛题已求解正确，也不保证比赛格式全部合规。

## 快速启动：Docker

安装 Git 和支持 Linux 容器的 Docker Compose，在终端运行：

```sh
git clone https://github.com/zhou2030109-glitch/Remit-Agent.git
cd Remit-Agent
docker compose -f docker-compose.release.yml up -d --build
```

打开 <http://localhost:18000>，在界面里的模型连接设置中填写自己的 API 地址、密钥、模型名和协议。首次构建包含科学计算库、中文字体和 LaTeX，下载量较大。模型服务费用由自己的供应商收取。

容器默认使用 Python 计算。配置与任务保存在命名数据卷中，`docker compose -f docker-compose.release.yml down` 停止服务并保留数据；`down -v` 会删除这些数据。

## Windows 源码启动

需要 Python 3.12、uv、Node.js 24、pnpm 10。仓库包含 Windows 启动器所需的 Redis 运行文件及许可证。

```powershell
git clone https://github.com/zhou2030109-glitch/Remit-Agent.git
cd Remit-Agent
cd backend
uv sync --locked
Copy-Item .env.example .env.dev
cd ../frontend
pnpm install --frozen-lockfile
Copy-Item .env.example .env.development
cd ..
.\win_start.bat
```

打开 <http://localhost:15173>。用 `win_stop.bat` 停止本项目服务。`win_start.bat --check` 检查启动依赖。

- 模型密钥在界面保存到本机配置，仓库不提供密钥。
- MATLAB 可选，需要自行安装并具备可用许可证；默认优先 MATLAB，不可用时按配置回退 Python。可在 `backend/.env.dev` 设置 `CODE_EXECUTION_BACKEND=python`。
- 本机导出论文 PDF 需安装 XeLaTeX（TeX Live 或 MiKTeX）与中文字体；Docker 方案已包含这些组件。
- macOS/Linux 源码部署另需安装 Redis，参考 [开发说明](docs/development.md)。

## 第一次使用

1. 配置四个角色的模型连接，检查连接状态。
2. 新建项目，选择赛事并导入题面和数据。可先使用 `backend/app/example/urban_cooling/` 中的合成小例子。
3. 与协调手确认题意和计划，再启动计算。方案、关键结果与论文均需检查。
4. 在“文件与结果”查看可追溯产物，在“论文”编辑、编译并导出。

赛事适配包含国赛、华为杯、美赛、华数杯等配置和开源基础技能；当届规则以主办方文件为准。详见 [赛事适配范围](docs/competition-adapters.md)。

## 仓库内容

```text
backend/app/     后端、角色、执行器和赛事技能
frontend/src/    对话、成果阅读与论文编辑界面
backend/tests/  后端回归测试
frontend/tests/ 前端行为测试
tests/          启动器与安装契约测试
tools/          启动、打包与可选资料库工具
docs/           使用与开发文档
```

不包含本机密钥、真实赛题附件、对话与运行记录、个人论文库、截图、虚拟环境或构建产物。可选论文库默认为空；通用写作技能与有许可的开源技能仍可使用。

## 测试

```sh
cd backend
uv run pytest tests -q
cd ../frontend
pnpm test
pnpm build
```

更多验证范围见 [发布验证](docs/release-validation.md)。本地执行模型生成的代码会使用本机权限；请在可信本机使用，处理不可信代码时选择隔离环境。该版本不提供多用户身份认证，不应直接暴露为公共网站。

## 许可与来源

Remit 自有代码使用 [MIT](LICENSE)。第三方依赖、Windows Redis 运行库和导入技能保留各自许可。项目历史来源及适用范围请同时阅读 [NOTICE](NOTICE.md)、[第三方声明](THIRD_PARTY_NOTICES.md) 和 [来源审计](docs/originality-audit.md)。
