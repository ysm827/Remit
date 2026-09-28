# Remit 赛事技能资料

`competitions.json` 保存赛事配置，`vendor/` 保存来自开源项目的参考文本，`sources.lock.json` 记录逐文件来源、固定提交、MIT 许可和 SHA-256。检索日期为 2026-09-27。

## 来源

- [anticipate218/math-modeling-skill](https://github.com/anticipate218/math-modeling-skill/tree/387bea0d9ffa00b8642d9ca988c7f360688d4322)：国赛、美赛、研究生赛的建模和写作知识。保留 LICENSE、主技能、参考文档和轻量 LaTeX 资产。
- [sweetcornna/mathodology](https://github.com/sweetcornna/mathodology/tree/0cfcd93f1dc8ddd26f928f7ec88a09ae3a1d70f6)：Agent 流程、证据检索、质量检查与赛事差异参考。保留 LICENSE、选定技能和工作流文档。

这是参考资料子集，不是上游项目的完整可执行安装。文中可能提到未导入的脚本、字体和辅助技能。Remit 不执行这些脚本，也不按上游说明安装依赖、修改权限或改变审批流程。不同赛事复用基础技能，再叠加各自配置；不代表找到了 21 套独立的赛事专属开源技能。

## 更新

1. 核查上游许可证及目标提交。保留上游原文和许可。
2. 将需要的文本放入 `vendor/`，更新锁文件中的路径、固定提交 URL 和哈希。
3. 在 `competitions.json` 关联 `skill_files`，填写当届官方来源、已验证条款和人工检查项。没有证据的条款保留待核实状态。
4. 运行 `tests/test_project_redesign.py`；模板变化还需真实编译验证。

项目创建时冻结技能内容、哈希和规则。更新目录不会静默改变已有项目；跨年份选择会撤销原年份的硬性版式限制，提示重新核对。

## 可选论文方法库

`writing/SKILL.md` 和 `writing/contests/` 提供通用写作与赛事论证指导。公开版 `writing/library.json` 默认为空，不分发个人论文、摘录和来源清单。用户可使用提取/提炼工具导入自己有权使用的资料；详见 [论文方法库](../../../docs/paper-library.md)。
