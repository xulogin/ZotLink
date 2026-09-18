# ZotLink 失败模式对照表

先跑 `python scripts/doctor.py`，它会把环境问题一次报全。

## Word / Refresh 相关

| 症状 | 真因 | 修法 |
|---|---|---|
| Refresh 弹"找不到此条目 / 请手动选择" | 字段里没写 `uris`，Zotero 只能靠 DOI 或标题反查 | 跑 `verify_docx.py`；报 "item has no uris" 就是 build 时 `zot_match_index.json` 缺了那条，重跑 `run.py` |
| Refresh 后引用变成 `(Author, Year)` 但参考文献列表是空的 | markdown 里没有 `[[bibliography: ...]]` 标记 | 加上；`build_doc.py` 其实已经 warning 过 |
| 参考文献里出现 `基金项目:` `ORCID:` `单位:` `中科院一区` `7.099Q1` | 库里条目的 `series`/`seriesTitle`/`extra` 被中文聚合器翻译器污染 | `zot_scan_dirty.py` 定位 → 关 Zotero → `zot_clean_dirty.py --yes` |
| 换了样式还是那些乱字 | 同上，所有标准 CSL 样式都会打印那些字段 | 同上，根治在库里，不在样式 |
| 引用格式不对 / 想换期刊样式 | — | Word → Zotero ribbon → Document Preferences → 选样式 → OK。**GUI 操作，脚本动不了**，不用重新生成 docx |
| 两处引用指向了同一篇文献 | 两个 citekey fuzzy 匹配到同一个条目 | `zot_match.py` 的碰撞检测会保留强匹配、把弱的退回 missing；看 report 里的 "Collisions resolved" 一节 |

## 匹配相关

| 症状 | 真因 | 修法 |
|---|---|---|
| `miss > 0`，但文献明明已经导进 Zotero 了 | 导进了 group library 而不是 User Library；或 Zotero 数据目录不是脚本读的那个 | `doctor.py` 会打印实际读的 `zotero.sqlite` 路径和条目数，对一下 |
| 脚本说库是两年前的旧库 / 找不到新条目 | Zotero 数据目录被改到非默认位置 | 自动探测读的是 profile 里的 `extensions.zotero.dataDir`；探测不到就在项目里放 `zotlink.json`：`{"zotero_data_dir": "D:/Zotero"}` |
| 某条一直 `AMBIG` | 库里有多份重复且标题不完全一样 | 去 Zotero 里合并重复条目（选中 → 右键 → Merge Items）。AMBIG 条目**不会**被写进 `references_missing.bib`，因为再导只会多一份 |
| 匹配上了但明显是错的文献 | 走了 `title-fuzzy` 策略 | 看 `reports/zot_match_report.md` 的 strategy 列；给 bib 条目补上正确 DOI 是最快的修法 |
| miss 的条目自动导入后还是 miss | bib 条目的 DOI/标题本身是错的（比如是编的） | 核对原文；编造的文献会在库里留下垃圾条目，去 Zotero 删掉 |

## 连接 / 环境相关

| 症状 | 真因 | 修法 |
|---|---|---|
| "Zotero is not reachable on 127.0.0.1:23119" 但 Zotero 明明开着 | 机器上设了 `HTTP_PROXY`/`HTTPS_PROXY`，urllib 把 localhost 也走代理 | ZotLink 已用 `ProxyHandler({})` 绕开；若自己写探针脚本记得照做，或临时 `set NO_PROXY=127.0.0.1` |
| 同上，且没有代理 | Zotero 设置里没开本地访问 | Zotero → 编辑 → 设置 → 高级 → 勾"允许其他应用通过本机访问 Zotero" |
| `zot_clean_dirty.py` 报 "database is locked" | Zotero 还在跑（任务管理器里有 zotero.exe） | 彻底关掉再跑。这是安全栏，不要绕过 |
| `pandoc not found in PATH` | 没装 pandoc，或装完没重开终端 | <https://pandoc.org/installing.html> |
| `python-docx is not installed` | — | `pip install python-docx` |
| 控制台输出乱码 / `UnicodeEncodeError` | Windows 控制台是 GBK | 脚本已经 `reconfigure(encoding="utf-8")`；自己加 print 时别用花哨符号，或设 `PYTHONIOENCODING=utf-8` |
| `no ZotLink project found` | 当前目录不在项目里 | `cd` 进项目，或加 `--project "<目录>"` |

## 灾难恢复

- `zot_clean_dirty.py` 每次动库前自动备份成 `zotero.sqlite.bak-<时间戳>`（和库同目录）。
  回滚：关掉 Zotero，`copy /Y "<数据目录>\zotero.sqlite.bak-xxx" "<数据目录>\zotero.sqlite"`
- docx 丢了：只要 `data/references.bib` + `content/*.md` 还在，重跑 `run.py` 就重建
- `reports/` 整个删掉都没关系，重跑会重生
