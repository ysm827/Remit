# 可选论文方法库

公开版不包含开发者的私人论文、摘录或文件清单。通用写作技能及有开源许可的参考技能仍会载入，`backend/app/competition_skills/writing/library.json` 初始为空。

如需建立自己的方法库，请仅导入有权使用的论文。`tools/extract_paper_library.py --help` 与 `tools/distill_paper_library.py --help` 提供提取和分析参数；提炼会调用你配置的模型并产生费用。工具在导出前核验选页引文，不保证原论文科学结论正确。

方法卡只用于借鉴论证方式，不能作为新任务结果或引文来源。个人资料和生成方法卡不应提交到公共仓库。

本地方法库放在用户配置文件所在目录下的 `project/paper_library/library.json`，存在时优先读取。源码运行对应 `backend/project/paper_library/library.json`，此目录被 Git 忽略。通用技能仍从随包目录载入。
