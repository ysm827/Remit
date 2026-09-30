# 升级到 Remit 2.0 与回退

Remit 2.0 继续使用 `zhou2030109-glitch/Remit` 仓库。商标、群聊二维码、Star History 及原仓库的提交历史保留，原 Remit-Agent 开发历史也并入这里。

## 升级前

1. 保存工作并正常退出正在运行的 Remit。
2. 备份本机配置、项目和论文；这些内容不在公开仓库中。
3. 不在唯一的数据副本上试跑升级，也不要让两个版本同时写入同一任务目录。

源码模式需备份 `backend/.env.dev`、`backend/project/` 及自定义资源。桌面模式需备份整个用户数据目录：Windows 为 `%LOCALAPPDATA%\Remit\Desktop`，macOS 为 `~/Library/Application Support/Remit`。

## 安装 2.0

建议在新目录克隆，保留原程序和数据目录以便回退：

```sh
git clone --branch v2.0.0 https://github.com/zhou2030109-glitch/Remit.git Remit-2.0
cd Remit-2.0
```

按 README 安装源码依赖，或从 `v2.0.0` Release 下载与电脑架构相符的安装包。没有 `.exe` / `.dmg` 附件时，安装包尚未交付，不要把旧预览安装包当成 2.0。

复制配置前对照新版 `.env.example` 检查字段；模型密钥仍保存在本机。先新建小项目验证连接、计算和论文导出，再使用实际赛题。

升级会应用新的论文和对话规则，但不会自动改写旧论文或重算旧结果。旧任务断点结构的全面兼容性尚未验收，不能保证旧工作流可直接跨版本恢复。

## 获取升级前版本

```sh
git clone --branch legacy/pre-2.0 https://github.com/zhou2030109-glitch/Remit.git Remit-legacy
cd Remit-legacy
git switch --detach archive/pre-2.0-20260930
```

这会取得升级前原仓库的准确源码 `d9b0aa62655e08a8421c63eb5a5d05461252b22b`。按该版本 README 安装其依赖，并使用升级前备份的数据。不要直接用旧版打开已经被新版修改的数据；保留一份独立副本。

## 品牌与社区资源

原始图标保存在 `assets/remit-icon.*` 与 `assets/remit-m-icon.*`，应用前端继续使用原图标。群聊码保存在 `assets/remit-wechat-group-20260929.png`；图片注明有效期为 2026 年 10 月 6 日前，过期需要更新二维码。

Star 曲线仍读取本仓库 `star-history` 分支，原自动更新工作流保留。存档标签和 Git 历史用于保留代码版本，用户项目数据仍需自行备份。
