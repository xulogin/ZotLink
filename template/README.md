# {{TITLE}}

用 [ZotLink](https://github.com/xulogin/ZotLink) 管线写作：Markdown 正文 +
BibTeX 文献 → 带 Zotero 活动字段的 docx，在 Word 里 Refresh 即可自动生成
正文引用和参考文献列表，随时一键切换期刊样式。

## 目录

| 路径 | 谁改 | 说明 |
|---|---|---|
| `content/{{NAME}}.md` | 你 | 正文，引用写 `[[cite:key]]` |
| `data/references.bib` | 你 | 文献源，key 风格 `lastname+YYYY+word` |
| `data/references.json` | 脚本 | pandoc 生成的 CSL JSON，别手改 |
| `reports/` | 脚本 | 匹配报告 / 脏字段报告，删了会重生 |
| `output/{{NAME}}.docx` | 脚本 | 最终产物 |
| `zotlink.json` | 你（可选） | 本机配置，如 `{"zotero_data_dir": "D:/Zotero"}` |

## 跑一次

最省事：在本目录开 Claude Code，直接说「我改了正文，重跑」，或者用 `/zotlink`。

手动跑（`<ZotLink>` = ZotLink 插件 / 仓库根目录）：

```powershell
cd "<本项目目录>"
python "<ZotLink>\scripts\run.py"
python "<ZotLink>\scripts\verify_docx.py"
```

然后打开 `output/{{NAME}}.docx` → Word 顶部 Zotero → **Refresh**。

换期刊样式：Word → Zotero → Document Preferences → 选样式 → OK，
全文引用和参考文献列表会一起重排，不用重新生成 docx。
