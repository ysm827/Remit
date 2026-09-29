## Remit 桌面预览版（未签名）

保留 Remit 原有图标与简约工作台，安装后打开本机浏览器使用。

本版修复建模完成后“继续”误入建模恢复的问题，论文中断时可续写已保存的章节；生成初稿后自动打开并准备 PDF 预览，保留已有手工编辑。

论文章节校验发现缺项时，会把具体反馈交回论文手修订一次；再次失败则保存诊断并停止，不发布未通过的章节。论文正文与聊天回复采用不同的表达要求。

修复科学计数法被拆成两个数字导致的误报；恢复时会重新校验已保存的章节草稿，通过后直接复用。

- Windows：下载 `Windows-x64-Setup.exe`，按向导安装。
- Apple 芯片 Mac：下载 `macOS-arm64.dmg`，将 Remit 拖入 Applications。
- Intel Mac：下载 `macOS-x64.dmg`，将 Remit 拖入 Applications。
- 每个安装包附有 SHA-256 校验文件。

内置 Python、常用科学计算库、Redis、Pandoc、XeLaTeX 与 Fandol 中文字体。
首次打开需要填写自己的模型服务地址、模型名称和密钥；联网模型调用按所选服务计费。
MATLAB 及其工具箱需要单独安装并持有许可证，默认使用包内 Python。

这是未签名、未公证的预览版，Windows / macOS 可能显示发布者验证提示。
macOS 需要 15 或更新版本；Windows 面向 64 位 Windows 10/11。
不包含作者的密钥、个人配置、项目附件、运行记录或研究资料。

项目与设置保存在用户数据目录，升级或卸载程序时保留：

- Windows：`%LOCALAPPDATA%\Remit\Desktop`
- macOS：`~/Library/Application Support/Remit`

自动检查包含独立 Python 内核、科学计算、CSV 和中文 PNG、Pandoc 转换、三套论文模板的 PDF 编译与逐页渲染，以及 Redis / 后端 / 前端启动。
自动检查不证明所有模型供应商、所有竞赛题或 MATLAB 环境均已验证。
