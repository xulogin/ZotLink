# ZotLink

**Markdown 正文 + BibTeX 文献 → 带 Zotero 活动字段的 Word 文档。**
在 Word 里点一次 Zotero → Refresh，全文引用和参考文献列表自动成型；之后换期刊
样式（RSE / ISPRS / GB-T 7714 / Nature …）只需在 Word 里选一下，不用重新生成文档。

同时是一个 [Claude Code](https://claude.com/claude-code) / Codex **插件**——一条命令
装好之后，直接说「加一篇关于 X 的文献，引用在第二段」「我改了正文，重跑」
「参考文献里有奇怪的字」，它就按这套管线执行。

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

## 最简单的用法

**一、让 AI 装上它。** 打开 Claude Code 或 Codex，直接说：

> 安装 https://github.com/xulogin/ZotLink

**二、直接提需求。** 比如：

> 帮我起一篇关于遥感大数据的引言，找 5 篇高引文献引上

或者在已有的写作项目里：

> 加一篇关于 X 的文献，引用在第二段
>
> 我改了正文，重跑
>
> 参考文献里出现了「基金项目」「中科院一区」这种乱字，清一下

剩下的它自己干：查 DOI 核实 → 写进 `references.bib` → 匹配 Zotero 库
（库里没有的自动导入）→ 生成 docx → 拆开 docx 逐字段核对 → 才交给你。
**中间那些命令都是 AI 自己敲的，你一条都不用输。**

最后你只做一件事：打开 `output\*.docx` → Word 顶部 Zotero → **Refresh**。

## 手动装（可选）

想自己装也行，两条命令：

```text
Claude Code:   /plugin marketplace add https://github.com/xulogin/ZotLink.git
               /plugin install zotlink@zotlink

Codex:         codex plugin marketplace add https://github.com/xulogin/ZotLink.git
               codex plugin add zotlink@zotlink
```

需要 Python 3.8+（带 `python-docx`）、pandoc、Zotero 7/8 和 Word 的 Zotero 插件。
**不需要 Better BibTeX**。Zotero 数据目录会自己从 profile 的 `prefs.js` 读出来。

**用别的 AI 工具？** Gemini CLI / Cursor / Cline 没有插件市场，`git clone` 下来
让你的 AI 读一遍 `AGENTS.md` 就行。通义灵码 / Zed / GitHub Copilot 会自动读 `AGENTS.md`。

**不用 AI，只当命令行工具**也行，clone 下来直接调 `scripts/` 里的脚本
（下面 `<ZotLink>` 就是仓库根目录）：

```powershell
python <ZotLink>\scripts\doctor.py                       # 自检
python <ZotLink>\scripts\new_project.py "D:\paper\intro" --title "引言" --name introduction
cd "D:\paper\intro"                                      # 填 bib + 写正文
python <ZotLink>\scripts\run.py                          # 跑管线
python <ZotLink>\scripts\verify_docx.py                  # 核对（"跑通" ≠ "对"）
```

`examples/demo/` 是一个五条文献的最小可跑样例，
`python <ZotLink>\scripts\selftest.py` 会拿它端到端验一遍安装。

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

- [`skills/zotlink/SKILL.md`](skills/zotlink/SKILL.md) — 给 Claude 看的操作手册
- [`skills/zotlink/references/internals.md`](skills/zotlink/references/internals.md) — URI 匹配原理、匹配策略优先级、docx 字段结构
- [`skills/zotlink/references/gotchas.md`](skills/zotlink/references/gotchas.md) — 实跑撞出来的坑（代理 502、中文排版空格、AMBIG 重复导入 …）
- [`skills/zotlink/references/troubleshooting.md`](skills/zotlink/references/troubleshooting.md) — 失败模式对照表

## License

MIT
