# ZotLink

这个仓库是一个 Zotero ↔ Word 引文管线，同时是 Claude Code / Codex 插件。

**所有操作规矩写在 [`skills/zotlink/SKILL.md`](skills/zotlink/SKILL.md)，动手前先读它。**

补充材料：

- `skills/zotlink/references/gotchas.md` — 实跑撞出来的坑，动手前扫一眼
- `skills/zotlink/references/internals.md` — URI 匹配原理、匹配策略、docx 字段结构
- `skills/zotlink/references/troubleshooting.md` — 失败模式对照表

三条铁律：文献不许编（DOI 去 Crossref 核）、跑完必须 `verify_docx.py` 核对、
动 Zotero 库前必须先关 Zotero。
