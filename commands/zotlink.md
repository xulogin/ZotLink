---
description: "Zotero ↔ Word 引文管线：加文献 / 改正文重出 docx / 清参考文献乱字。不带参数就跑一次环境自检。"
---

调用 zotlink skill（`zotlink:zotlink`），严格按它的规矩执行。

用户输入：$ARGUMENTS

---

## 没有输入内容时 → 跑环境自检

```bash
python "<ZotLink>/scripts/doctor.py"
```

用大白话报结果：

- **全绿** → 「环境正常。告诉我项目在哪、或者让我新建一个就能开工。」
- **缺 pandoc / python-docx** → 说清装哪个（`pip install python-docx`，pandoc 去官网），别糊原始输出
- **找不到 zotero.sqlite** → 让用户在 Zotero → 编辑 → 设置 → 高级 里看「数据存储位置」，
  然后写进项目的 `zotlink.json`
- **connector 那条是 warn 不是 fail** → 只有要自动导入新文献时才需要 Zotero 开着

## 有输入内容时

按 SKILL.md 的「常见任务」表对号入座。三条不能省：

1. 文献 DOI 必须去 `https://api.crossref.org/works/<DOI>` 核实，**不许编**
2. 跑完 `run.py` 必须再跑 `verify_docx.py`，不许只看「没报错」
3. 要动 Zotero 库（清脏字段）之前，必须让用户先把 Zotero 完全关掉
