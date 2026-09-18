# ZotLink

**Markdown 正文 + BibTeX 文献 → 带 Zotero 活动字段的 Word 文档。**
在 Word 里点一次 Zotero → Refresh，全文引用和参考文献列表自动成型；之后换期刊
样式（RSE / ISPRS / GB-T 7714 / Nature …）只需在 Word 里选一下，不用重新生成文档。

同时是一个 [Claude Code](https://claude.com/claude-code) skill —— 装好之后直接对
Claude 说「加一篇关于 X 的文献，引用在第二段」「我改了正文，重跑」「参考文献里
有奇怪的字」，它就按这套管线执行。

---

## 它解决的问题

自己拼 docx 的常见做法，是在引文字段里写 `itemData` + 一个数字 `id`。Zotero 在
Refresh 时找不到这个 id，就退化成按 DOI 反查、再退化成按标题模糊匹配，于是
**一篇一篇地弹"请选择条目"对话框**。文献一多就没法用。

ZotLink 的做法是**先绑定再生成**：直接读 `zotero.sqlite`，把每个 citekey 解析
成库里真实的 itemKey，再把真实 URI

```
http://zotero.org/users/local/<localUserKey>/items/<itemKey>
```

烘焙进 docx 的 `CSL_CITATION` 字段。Refresh 时 Zotero 按 URI 一查就到——零弹窗。

顺带解决另一个中文用户的老问题：CNKI / 茉莉花 / 中科院分区插件会往条目的
`series`、`extra` 字段里塞基金号、ORCID、影响因子、分区标签，标准 CSL 样式会把
它们原样打印进参考文献。管线里带了扫描和清理（自动备份 + 单事务 + Zotero 必须关闭）。

## 环境要求

| 依赖 | 说明 |
|---|---|
| Python ≥ 3.8 | 加 `python-docx`：`pip install python-docx` |
| pandoc | BibTeX → CSL JSON，<https://pandoc.org/installing.html> |
| Zotero 7 / 8 | **不需要 Better BibTeX**，自动导入走标准 connector |
| Word + Zotero 插件 | 最后的 Refresh 这一步 |

Zotero 数据目录和 localUserKey 都是自动探测的（读 profile 的 `prefs.js` 和
`zotero.sqlite` 的 settings 表），一般不用配任何东西。

## 安装

### 作为 Claude Code skill

```powershell
git clone https://github.com/xulogin/ZotLink "$env:USERPROFILE\.claude\skills\zotlink"
```

macOS / Linux：

```bash
git clone https://github.com/xulogin/ZotLink ~/.claude/skills/zotlink
```

重开 Claude Code，`/zotlink` 就在了。

### 只当命令行工具用

clone 到任何地方，直接调 `scripts/` 下的脚本即可，skill 部分不影响使用。

## 用法

```powershell
# 0. 自检
python <ZotLink>\scripts\doctor.py

# 1. 新建一个写作项目
python <ZotLink>\scripts\new_project.py "D:\paper\intro" --title "引言" --name introduction

# 2. 往 data/references.bib 里加 BibTeX，往 content/introduction.md 里写正文
#    引用标记：[[cite:key]] / [[cite:key1;key2]]

# 3. 跑管线
cd "D:\paper\intro"
python <ZotLink>\scripts\run.py

# 4. 核对（"跑通" ≠ "对"）
python <ZotLink>\scripts\verify_docx.py
```

然后打开 `output\introduction.docx` → Word 顶部 Zotero → **Refresh**。

`examples/demo/` 是一个五条文献的最小可跑样例，可以直接拿它验证安装。

## 项目结构

```
<你的项目>/
├── content/<名字>.md        ✏️ 正文，引用写 [[cite:key]]
├── data/references.bib      ✏️ 文献源
├── data/references.json     ⚙️ pandoc 生成，别手改
├── reports/                 ⚙️ 匹配报告 / 脏字段报告，删了会重生
├── output/<名字>.docx       ⭐ 最终产物
└── zotlink.json             可选，本机配置
```

## 脚本

| 脚本 | 作用 |
|---|---|
| `run.py` | orchestrator，一条命令跑完全流程 |
| `doctor.py` | 环境自检 |
| `new_project.py` | 按模板新建项目 |
| `zot_match.py` | citekey → Zotero itemKey 匹配，出报告和 `references_missing.bib` |
| `zot_scan_dirty.py` | 扫聚合器污染字段（只读）|
| `zot_clean_dirty.py` | 清理脏字段（**会写库**：Zotero 必须关，自动备份，单事务）|
| `build_doc.py` | Markdown → 带 Zotero 字段的 docx |
| `verify_docx.py` | 拆开 docx 核对引用字段，Refresh 前的门禁 |
| `zot_env.py` | 路径 / 库身份 / 连接的统一解析 |

所有脚本都接受 `--project <目录>`；不传就从当前目录往上找项目根。

## 正文语法

````markdown
---
title: 文档标题
---

# 一级标题

正文……单篇引用 [[cite:calders2020terrestrial]]，合并引用
[[cite:calders2020terrestrial;disney2019terrestrial]] 会变成一个括号。

(1) **编号条目**：粗体引导语后面接正文 [[cite:wangd2020lewos]]。

%% 以 %% 开头的行是注释，不会进 docx

[[bibliography: 参考文献 / References]]
````

同一段内换行自动接续：汉字之间不补空格，汉字接 Latin（引用括号就在这）补空格，遇到中文标点不补；空行分段。
排版（Times New Roman + 宋体/黑体、1.5 倍行距、0.74 cm 首行缩进）写在
`build_doc.py` 的 `add_*` 函数里，要改版式改那里。

## 更多

- [`SKILL.md`](SKILL.md) — 给 Claude 看的操作手册
- [`references/internals.md`](references/internals.md) — URI 匹配原理、匹配策略优先级、docx 字段结构
- [`references/gotchas.md`](references/gotchas.md) — 实跑撞出来的坑（代理 502、中文排版空格、AMBIG 重复导入 …）
- [`references/troubleshooting.md`](references/troubleshooting.md) — 失败模式对照表

## License

MIT
