---
name: zotlink
description: Use when a manuscript's citations live in Zotero and the deliverable is a Word .docx — adding or citing a reference, rebuilding after editing the text, Refresh popping up "select the right item", junk like 基金项目 / ORCID / 中科院一区 / 7.099Q1 appearing in the reference list, switching journal citation styles, or starting a new Zotero-linked writing project. 触发词：Zotero、参考文献、引用、文献管理、bib、BibTeX、投稿 docx、Word 引文、换期刊样式、参考文献乱字。
---

# ZotLink — Zotero ↔ Word 引文管线

## 这是什么

正文写 Markdown，文献写 BibTeX，一条命令生成**带 Zotero 活动字段的 docx**。
在 Word 里点一次 Zotero → Refresh，全文引用和参考文献列表自动成型，之后随时
换期刊样式（RSE / ISPRS / GB-T 7714 / Nature …）都不用重新生成文档。

**核心招数**：把每条文献**预先静态绑定**到 Zotero 库里那个具体条目的 itemKey，
把真实 URI `http://zotero.org/users/local/<key>/items/<itemKey>` 烘焙进 docx 的
CSL_CITATION 字段。Refresh 时 Zotero 按 URI 一查就到——不弹窗、不靠 DOI 反查、
不靠标题模糊匹配。这就是它和"手动插引用"的全部区别。

## 什么时候用

- 用户要在一个 Zotero 联动的项目里**加文献 / 引用文献 / 改正文后重出 docx**
- Word 里 Refresh **弹"请选择条目"**，或参考文献里出现 `基金项目:` `ORCID:`
  `中科院一区` `7.099Q1` `姓名:` 这类乱字
- 用户要**新开**一个 Zotero 联动的写作项目
- 用户问**怎么换期刊引文样式**

不适用：不需要 Zotero 的纯 Markdown→docx 转换（直接用 pandoc 就行）。

## 工具在哪（下面写 `<ZotLink>` 的地方全指它）

**`<ZotLink>` = 本文件所在目录的上两级**（本文件是 `<ZotLink>/skills/zotlink/SKILL.md`）。

- **Claude Code**：可以直接用 `${CLAUDE_PLUGIN_ROOT}`，会自动展开成绝对路径
- **Codex / 其他环境**：`${CLAUDE_PLUGIN_ROOT}` **不会展开**。先把 `<ZotLink>` 算成
  实际绝对路径再执行，**不要把 `${...}` 原样敲进终端**
- **没装插件、直接 clone 的**：`<ZotLink>` 就是仓库根目录

无论哪种情况，**都不要问用户路径**——你自己能算出来。

## 一条命令跑全程

```powershell
cd "<项目目录>"
python "<ZotLink>/scripts/run.py"
```

`run.py` 按顺序做完这六步，已经是最新的会自动跳过：

| # | 步骤 | 干什么 |
|---|---|---|
| 1 | pandoc | `data/references.bib` → `data/references.json`（bib 更新了才跑）|
| 2 | zot_match | 每个 citekey 映射到 Zotero 里真实 itemKey，出报告 |
| 3 | 自动导入 | miss>0 且 Zotero 在跑 → POST 到 `/connector/import`，再重匹配 |
| 4 | zot_scan_dirty | 扫中文聚合器污染的字段 |
| 5 | 清理 | dirty>0 → 提示关 Zotero 跑 clean（`--auto-clean` 可自动）|
| 6 | build_doc | 生成 `output/<名字>.docx` |

跑完**必须验一遍**，别只看"没报错"：

```powershell
python "<ZotLink>/scripts/verify_docx.py"
```

它拆开 docx 的 `word/document.xml`，核对引用字段数 == 正文标记数、每个
citationItem 都带 `uris`、每个 URI 的 itemKey 都在匹配索引里。这一步不过，
Word 里 Refresh 就会弹窗。

## 正文语法（`content/*.md`）

```markdown
---
title: 文档标题
---

# 一级标题

正文……单篇引用 [[cite:calders2020terrestrial]]，
合并引用 [[cite:calders2020terrestrial;disney2019terrestrial]] 会变成一个括号。

(1) **编号条目**：粗体引导语后面接正文 [[cite:wangd2020lewos]]。

%% 以 %% 开头的行是注释，不会进 docx

[[bibliography: 参考文献 / References]]
```

同一段内换行自动接续：汉字之间不补空格，汉字接 Latin（引用括号就在这）补空格，遇到中文标点不补；空行分段。
`[[bibliography]]` 是参考文献占位符，Refresh 时被替换成正式列表；漏了它
build 会给出 warning。

## 常见任务

| 用户说 | 你做 |
|---|---|
| "加一篇关于 X 的文献，引用在第 N 段" | 查到真实 DOI/BibTeX（**不许编造**）→ 追加进 `data/references.bib`（key 用 `姓+年份+首个实词`，重姓加名首字母如 `liuc`/`liuj`）→ 在 md 里插 `[[cite:key]]` → 跑 run.py → 跑 verify_docx.py |
| "我改了正文，重跑" | 直接 run.py（前几步自动跳过，几秒出 docx）|
| "参考文献里有奇怪的字 [贴一段]" | 跑 `<ZotLink>/scripts/zot_scan_dirty.py` 定位 → 让用户**关掉 Zotero** → `<ZotLink>/scripts/zot_clean_dirty.py --yes`（自动备份 + 事务）→ 让用户重开 Zotero 和 Word 再 Refresh |
| "参考文献里英文文献也写成「等」/ 想让中文出「等」英文出 et al." | GB/T 7714 样式自带 CSL-M 双语开关但被注释掉了。跑 `python "<ZotLink>/scripts/fix_bilingual_style.py"` 生成一个双语副本（不动原样式）→ 让用户**完全退出再重开 Zotero** → Word → Document Preferences 选新样式 → Refresh。**先跑 `zot_language.py` 体检**：开关靠每条的 `language` 字段决定走哪条布局，字段为空的英文文献照样出「等」 |
| "language 字段乱 / 空" | `python "<ZotLink>/scripts/zot_language.py" [--all]` 只读体检出报告；要真改得让用户**关掉 Zotero** 再 `--fix`（自动备份 + 单事务）|
| "切到 Nature 样式" | 告诉用户：Word → Zotero ribbon → Document Preferences → 选样式 → OK。**这步是 GUI，脚本动不了**，全文引用会一起重排，不用重新生成 docx |
| "新建一个项目叫 X" | `python "<ZotLink>/scripts/new_project.py" <目录> --title "X" --name <文件名>` |
| "环境是不是配好了" | `python "<ZotLink>/scripts/doctor.py"` |

## 硬规矩

1. **交付前必须实跑 + verify_docx，不许只静态看一眼说"应该没问题"。**
   "跑通" ≠ "对"：匹配错条目也是零报错。回头看 `reports/zot_match_report.md`
   里每条用的什么策略——全是 `doi` 才算稳，出现 `title-fuzzy` 必须人眼确认。
2. **文献信息一个字都不许编。** 写进 `references.bib` 前，每条 DOI 都去
   `https://api.crossref.org/works/<DOI>` 核一遍 title / 作者 / 卷期页。
   `/connector/import` 照单全收、不验真伪，编的条目会变成垃圾进用户的库。
3. **`zot_clean_dirty.py` 会写 Zotero 数据库，Zotero 必须完全关闭。**
   脚本自己有 connector ping + 锁探测两道栏，不要绕过。
4. **`data/references.json`、`reports/*` 是生成物，别手改**，删了重跑会重生。

## 几个一定会踩的坑（完整清单见 `references/gotchas.md`）

- **Zotero 明明开着却连不上**：机器上有 `HTTP_PROXY` 时，urllib/curl 连
  `127.0.0.1:23119` 也走代理，返回 **502**，看起来和"没开"一模一样。
  必须用 `zot_env.local_opener()`（`ProxyHandler({})`）绕开。
- **在正文里举例写 `[[cite:a;b]]` 会被当成真引用**直接 FATAL。举例一律写在
  `%%` 注释行里。
- **Zotero 导入时会把标题改成 sentence case**，所以 bib 尽量带 DOI，
  别指望标题匹配。
- **AMBIG ≠ MISS**：库里已有但分不清哪份重复件的条目，**绝不能**再导一次，
  否则越导越多。`zot_match.py` 已把它们排除在 `references_missing.bib` 之外。
- **默认 Zotero 路径常常是空库**。怀疑匹配不上之前，先跑 `doctor.py` 看它
  实际读的是哪个 `zotero.sqlite`、多少条目。

## 等 / et al. —— 中英文分开输出

GB/T 7714-2015 要求 **and-others 跟着文献自己的语种走**：中文文献 `等`，
英文文献 `et al.`。Zotero 自带的 GB/T 样式用 CSL-M 多布局实现了这件事，
但**出厂是注释掉的**，所以全都打成「等」。两个前提缺一不可：

1. **样式要开双语布局** —— `fix_bilingual_style.py` 把 `<layout ... locale="en">`
   的注释去掉，另存成一个新 id/新标题的样式，原样式一个字节都不改。
2. **条目的 `language` 字段要是 citeproc 认得的值**（`en` / `en-US` / `zh` …）。
   空值或 `中文;` / `english` 这种自由文本匹配不上，会一律落回默认（中文）布局。
   `zot_language.py` 体检 + 规范化：先认用户自己写的标注，认不出再看标题是不是 CJK，
   **没标题就不猜**。

改完样式必须让用户**完全退出再重开 Zotero**——样式列表只在启动时扫描。

## 环境与配置

Zotero 数据目录**自动探测**（读 Zotero profile 的 `prefs.js`），localUserKey
自动从 `zotero.sqlite` 的 settings 表读。探测不到时按这个顺序覆盖：

```jsonc
// <项目目录>/zotlink.json
{ "zotero_data_dir": "D:/Zotero" }
```
或环境变量 `ZOTERO_DATA_DIR`。所有脚本都接受 `--project <目录>`，不传就从当前
目录往上找。依赖：Python ≥3.8 + `python-docx` + `pandoc`，Zotero 7/8（**不需要
Better BibTeX**，自动导入走标准 connector）。

## 更深的东西

- `references/gotchas.md` — 实跑撞出来的坑，动手前先扫一眼
- `references/internals.md` — URI 匹配原理、匹配策略优先级、脏字段清单、docx 字段结构
- `references/troubleshooting.md` — 失败模式对照表（Refresh 弹窗 / miss 不降 / 库被改路径 / database is locked …）
