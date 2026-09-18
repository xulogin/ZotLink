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

## 一条命令跑全程

```powershell
cd "<项目目录>"
python "$env:USERPROFILE\.claude\skills\zotlink\scripts\run.py"
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
python "$env:USERPROFILE\.claude\skills\zotlink\scripts\verify_docx.py"
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

同一段内的换行自动接续（只有两边都是 ASCII 时才补空格，中文之间不补），空行分段。
`[[bibliography]]` 是参考文献占位符，Refresh 时被替换成正式列表；漏了它
build 会给出 warning。

## 常见任务

| 用户说 | 你做 |
|---|---|
| "加一篇关于 X 的文献，引用在第 N 段" | 查到真实 DOI/BibTeX（**不许编造**）→ 追加进 `data/references.bib`（key 用 `姓+年份+首个实词`，重姓加名首字母如 `liuc`/`liuj`）→ 在 md 里插 `[[cite:key]]` → 跑 run.py → 跑 verify_docx.py |
| "我改了正文，重跑" | 直接 run.py（前几步自动跳过，几秒出 docx）|
| "参考文献里有奇怪的字 [贴一段]" | 跑 `zot_scan_dirty.py` 定位 → 让用户**关掉 Zotero** → `zot_clean_dirty.py --yes`（自动备份 + 事务）→ 让用户重开 Zotero 和 Word 再 Refresh |
| "切到 Nature 样式" | 告诉用户：Word → Zotero ribbon → Document Preferences → 选样式 → OK。**这步是 GUI，脚本动不了**，全文引用会一起重排，不用重新生成 docx |
| "新建一个项目叫 X" | `python scripts/new_project.py <目录> --title "X" --name <文件名>` |
| "环境是不是配好了" | `python scripts/doctor.py` |

## 硬规矩

1. **交付前必须实跑 + verify_docx，不许只静态看一眼说"应该没问题"。**
   "跑通" ≠ "对"：匹配错条目也是零报错。回头看 `reports/zot_match_report.md`
   里每条用的什么策略——`doi` / `title` 最稳，`title-fuzzy` 要人眼确认。
2. **`zot_clean_dirty.py` 会写 Zotero 数据库，Zotero 必须完全关闭。**
   脚本自己有锁检测和自动备份，但不要绕过它。
3. **文献信息不许编。** DOI、作者、年份查不到就说查不到，编造的 BibTeX 会
   在 match 阶段变成 miss，然后被自动 import 成一条垃圾条目进用户的库。
4. **`data/references.json`、`reports/*` 是生成物，别手改**，删了重跑会重生。

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

- `references/internals.md` — URI 匹配原理、匹配策略优先级、脏字段清单、docx 字段结构
- `references/troubleshooting.md` — 失败模式对照表（Refresh 弹窗 / miss 不降 / 库被改路径 / database is locked …）
