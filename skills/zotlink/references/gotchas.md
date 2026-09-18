# 踩过的坑（都是实跑撞出来的，不是想象的）

按"第一次会怎么栽"排序。每条都写清**症状 → 真因 → 怎么办**，别重蹈覆辙。

---

## 1. Zotero 明明开着，脚本说连不上

**症状**：`Zotero is not reachable on 127.0.0.1:23119`，但 Zotero 窗口就在眼前；
`curl http://127.0.0.1:23119/connector/ping` 返回 **502**。

**真因**：机器上设了 `HTTP_PROXY` / `HTTPS_PROXY`（VPN、clash、v2ray 那一类）。
`urllib` 和 `curl` **默认连 localhost 也走代理**，代理连不上 23119 就回 502——
这个 502 看起来和"Zotero 没开"一模一样。

**怎么办**：所有连 connector 的地方都必须用 `zot_env.local_opener()`
（内部是 `urllib.request.build_opener(ProxyHandler({}))`）。自己写探针脚本
也照做，或者临时 `set NO_PROXY=127.0.0.1`。

> 判别小技巧：`zot_env.zotero_alive()` 返回 True 而 curl 返回 502 → 就是代理问题。

---

## 2. 正文里想举例写 `[[cite:a;b]]`，结果 build 直接 FATAL

**症状**：`FATAL: citation key(s) not in references.bib: a, b`

**真因**：解析器不认识"这是个例子"，任何 `[[cite:...]]` 都当真引用。
写文档、写模板、写注释时最容易踩。

**怎么办**：用 `%%` 开头的注释行，整行不进 docx：

```markdown
%% 引用语法：[[cite:key]] / [[cite:key1;key2]]
```

---

## 3. 中文换行接续的空格，判据很容易写窄

**症状**：段落里冒出莫名其妙的空格，比如 `取代 "如何看得见"`；
或者反过来，引用括号紧贴汉字 `最值得投入的方向(Chi et al., 2016)`。

**真因**：软换行要不要补空格，**"两边是不是 CJK"这个判据是错的**——
中文正文里一堆字符不在 CJK 块里：弯引号 `“ ”`(U+201C/D)、破折号 `—`(U+2014)、
省略号 `…`(U+2026)。只判块，这些字符前面就会多一个空格。
但反过来"只要非 ASCII 就不补"也不对：汉字接 Latin（引用括号正好落在这里）
按中文排版规范**应该**留白（盘古之白）。

**怎么办**：按 Unicode 类别分三类（见 `build_doc.py::_char_class`）：

| 左 | 右 | 空格 | 例 |
|---|---|---|---|
| 汉字 | 汉字 | 无 | 普通中文换行 |
| 任一侧是 CJK 标点（`unicodedata.category` 以 `P` 开头的非 ASCII 字符）| — | 无 | `代` + `“` |
| 汉字 | ASCII | 有 | `方向` + `(Chi et al., 2016)` |
| ASCII | ASCII | 有 | 英文换行 |

---

## 3.5 `"放".isalnum()` 是 True —— 汉字算字母

**症状**：改完换行空格的判据，中文段落里变成 `并行计算 放在同一侧`，汉字之间多了空格。
更麻烦的是 **`verify_docx.py` 全绿**——它核对的是引用字段，不看排版。

**真因**：Python 的 `str.isalnum()` 对汉字返回 `True`（`Lo` 也算 alphanumeric）。
判据里写 `other.isalnum()` 想表达"对面是 Latin 字母数字"，结果汉字也命中了。

**怎么办**：两条。

1. 分支要写全，先把 `汉字 + 汉字 → 不补空格` 单独早退掉，
   再处理"一侧汉字一侧 ASCII"，这样 `isalnum()` 作用的一定是 ASCII 那侧。
2. **排版类改动必须肉眼看渲染出来的正文**，不能只看 `verify_docx` 绿灯。
   `scripts/selftest.py` 里有 `_needs_space` 的用例表，改判据先跑它。

```powershell
python "<ZotLink>/scripts/selftest.py"   # 含排版判据单测
```

## 4. 匹配报告的 Markdown 表格没有表头

**症状**：`zot_match_report.md` 打开是一堆竖线，表格渲染不出来。

**真因**：报告是按行号拼的，最后回填统计行时用了
`report_lines[4] = "- **matched: ...**"`——**索引 4 正好是表头行**，被冲掉了。

**怎么办**：用 `insert(4, ...)` 不要用赋值。凡是"按固定下标回填拼好的列表"
都要先数一遍那个下标现在是什么。

---

## 5. AMBIG 条目不能当成 missing 重新导入

**症状**：跑几次之后，Zotero 库里同一篇文献出现三四份重复件。

**真因**：早期版本把"没进 index 的 key"一律写进 `references_missing.bib`。
但 AMBIG（库里有多份重复、分不清用哪份）和 MISS（库里真没有）是两回事，
AMBIG 再导一次只会**再多一份**，下次更分不清，恶性循环。

**怎么办**：`zot_match.py` 里 AMBIG 的 key 单独收集、排除在 missing.bib 之外，
并打印提示让人去 Zotero 里手动合并（选中 → 右键 → Merge Items）。

---

## 6. 新建的项目第一次跑就失败

**症状**：`new_project.py` 建完项目，照着提示跑 `run.py`，直接 FATAL。

**真因**：模板正文里留了 `[[cite:key1]]` 这种示范标记，但 `references.bib`
是空的——脚手架产物开箱即坏，第一印象极差。

**怎么办**：模板里的语法示范全部放进 `%%` 注释行，正文只留一句普通话 +
一个 `[[bibliography]]`。**任何脚手架都应该"生成完立刻能跑通"**。

---

## 7. Zotero 导入后标题被改写，别拿标题当主键

**症状**：bib 里写的是 `Big Data for Remote Sensing: Challenges and Opportunities`，
导进 Zotero 后变成 `Big data for remote sensing: challenges and opportunities`。

**真因**：Zotero 的 BibTeX 翻译器会做 sentence-case 归一化。

**怎么办**：**bib 条目尽量带 DOI**。匹配策略里 `doi` 排第一档，标题类策略
（尤其 `title-fuzzy`）是兜底。看 `reports/zot_match_report.md` 的 strategy 列，
全是 `doi` 才算稳；出现 `title-fuzzy` 一定要人眼确认匹配对不对。

---

## 7.5 英文文献也被打成「等」—— 不是样式坏，是开关没开

**症状**：Refresh 出来的参考文献和正文引用，英文文献也写成 `Ma等, 2015`、
`CHI M, PLAZA A, BENEDIKTSSON J A, 等`。GB/T 7714-2015 要求
**中文文献用「等」、英文文献用「et al.」**，所以这是错的。

**真因**：两层，缺一不可。

1. Zotero 自带的 GB/T 7714 样式用 **CSL-M 多布局**实现双语
   （`<layout ... locale="en">` 一个给正文引用、一个给参考文献表），
   但**出厂就是注释掉的**，样式作者还在上面留了一行中文提示
   「取消这部分注释可以开启 CSL-M 的多语言功能」。默认状态下全都走中文布局。
2. 就算开了布局，citeproc 是按**每条文献的 `language` 字段**挑布局的。
   实测这个字段在真实库里非常脏：990 条里 273 条为空、还有
   `中文;` `英文;` `english` 这种自由文本。**空值和非 BCP-47 值都匹配不上 `locale="en"`**，
   于是英文文献照样落回中文布局，照样出「等」。

**怎么办**：

```powershell
python "<ZotLink>/scripts/zot_language.py" --all     # 先体检（只读）
# 关掉 Zotero 之后：
python "<ZotLink>/scripts/zot_language.py" --all --fix
python "<ZotLink>/scripts/fix_bilingual_style.py"    # 开样式的双语开关
```

注意三点：

- `fix_bilingual_style.py` **另存成新 id / 新标题的样式，不改原文件**，
  不想要删掉那个 .csl 就行
- 改完样式必须**完全退出再重开 Zotero**——样式列表只在启动时扫描
- 然后 Word → Zotero → Document Preferences 选新样式 → Refresh
- 规范化 `language` 时，**先认用户自己写的标注**（`英文;` → `en`），
  认不出再看标题是不是 CJK，**没有标题就不猜**

**顺带**：样式文件夹里常有现成的「双语」版本（文件名带「双语」或 `bilan`），
开关是打开的，但通常同时是「无 URL、DOI」版——换过去会丢 DOI。
所以宁可给当前样式打补丁，也别盲目换。

## 8. 「跑通」≠「对」

**症状**：零报错，docx 也出来了，Word 里 Refresh 一片弹窗。

**真因**：管线里每一步都可能"成功地做错事"——匹配到错的条目、citation 字段
少写了 `uris`、markdown 标记被吃掉。这些都不报错。

**怎么办**：**交付前必须跑 `verify_docx.py`**。它拆开 `word/document.xml`
逐项核对：引用字段数 == 正文标记数、每个 citationItem 都带 `uris`、
每个 URI 的 itemKey 都在匹配索引里、bibliography 字段数对得上。
这一步不过，Refresh 一定出问题。

---

## 9. 文献信息一个字都不许编

**症状**：miss 一直降不下去；或者更糟——被自动 import 成一条垃圾条目进了用户的库。

**真因**：编造的 DOI / 卷期页在 Zotero 里匹配不上任何真实条目，
而 `/connector/import` 是**照单全收**的，不会验证 DOI 是否真实存在。

**怎么办**：写进 `references.bib` 之前，**每条 DOI 都去 Crossref 核一遍**：

```
https://api.crossref.org/works/<DOI>
```

核 title / 作者全名顺序 / 期刊 / 年 / 卷期页。查不到就如实说查不到，不要凑。
（注意：`?select=author` 这种参数 Crossref 会返回 400，直接取完整记录。）

---

## 10. Windows 本机杂项

| 坑 | 说明 |
|---|---|
| 控制台 GBK | Python 打 `✓ → 【` 这类字符会 `UnicodeEncodeError`。脚本已 `sys.stdout.reconfigure(encoding="utf-8")`；自己加 print 时设 `PYTHONIOENCODING=utf-8` |
| PowerShell 5.1 没有 `&&` | 用 `;` 或 `if ($?) { ... }` |
| 默认 Zotero 路径可能是空库 | `%USERPROFILE%\Zotero` 常常是旧库/空库。真路径在 profile 的 `prefs.js` → `extensions.zotero.dataDir`，`zot_env` 已自动读；`doctor.py` 会打印实际读到的路径和条目数，**先看这个再怀疑别的** |
| `zotero.sqlite` 被 Zotero 占着 | 只读连接用 `nolock=1`；再失败就自动复制 db + `-wal` + `-shm` 到临时目录读快照（`zot_env.connect_ro`）|
| 清理脚本必须 Zotero 全关 | 有两道栏：connector ping + `BEGIN IMMEDIATE` 锁探测。别绕过，写坏的是用户的文献库 |
