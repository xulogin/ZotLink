# ZotLink 内部原理

## 1. 为什么必须写真实 URI

Zotero 的 Word 插件在 Refresh 时扫描 docx 里每个
`ADDIN ZOTERO_ITEM CSL_CITATION { ... }` 字段，按以下优先级找本地库条目：

1. **`citationItems[].uris[]`** — 形如
   `http://zotero.org/users/local/<localUserKey>/items/<itemKey>`，
   且 itemKey 在本地库存在 → **直接命中**，零歧义零弹窗
2. `citationItems[].id` — 当前会话的数字 itemID → 命中
3. 退化到 `itemData.DOI` 反查 → 库里 DOI 缺失或大小写不一致就失败
4. 退化到 `itemData.title` 模糊匹配 → 弹"请选择条目"对话框

大多数"自己拼 docx"的做法只写 `id` + `itemData`，于是永远走 3、4，遇到脏库就崩。
ZotLink 先用 `zot_match.py` 把每个 citekey 解析成真实 itemKey，再把第 1 条的 URI
烘焙进字段，所以一次过。

`uris` 里的 `localUserKey` 是 Zotero 给**未同步**本地库分配的随机 ID，存在
`settings` 表的 `account / localUserKey`。**已同步**账号用的是
`http://zotero.org/users/<userID>/items/<itemKey>`——`zot_env.library_uri_prefix()`
优先读 `userID`，没有才用 `localUserKey`，所以同步库和本地库都能跑。

## 2. 匹配策略与优先级

`zot_match.py` 直接读 `zotero.sqlite`（只读、`nolock=1`，Zotero 开着也能读；
读不动就自动落到临时快照）。逐条按强到弱试：

| 策略 | 条件 | 可信度 |
|---|---|---|
| `doi` | DOI 归一化后完全相同（去 `https://doi.org/` 前缀、转小写）| 最高 |
| `doi+dedup(n)` | DOI 命中多条但都是同一篇的重复件 | 最高 |
| `title+year` | 归一化标题相同 + 年份区分重名 | 高 |
| `title` / `title+dedup(n)` | 归一化标题相同（只保留 `[a-z0-9]`，所以 `3-D`==`3D`）| 高 |
| `author+year+word` | 第一作者姓 + 年份 + 标题首个实词 | 中 |
| `title-fuzzy` | 标题互为子串，**且两边都 >15 字符** | 低，要人眼确认 |

长度门槛那条是有来历的：中文标题归一化后只剩几个拉丁字母（比如只剩 `lidar`），
不设门槛会匹配上每一篇长英文标题。

重复条目用 `_pick_best_duplicate()` 收敛：**优先有 DOI 的，其次 itemID 最小
（最早导入的那份）**。

**碰撞检测**：两个 citekey 抢到同一个 itemKey 时，按策略强弱排序，强的留下，
弱的退回 missing，不会让两条引用指向同一条文献。

歧义条目（AMBIG）**不会**写进 `references_missing.bib`——那篇文献其实在库里，
只是分不清用哪个重复件，再导一次只会多出第三份。要去 Zotero 里手动合并。

## 3. 脏字段是怎么回事

中文聚合器的 Zotero 翻译器（CNKI、茉莉花/Jasminum、中科院分区插件等）会往
`series` / `seriesTitle` / `extra` / `archive` 这些字段里塞基金号、ORCID、
影响因子、分区标签。标准 CSL 样式会把它们**原样打印**进参考文献，于是出现：

> Calders, K. et al. 2020. …, *Remote Sensing of Environment*, 基金项目: 国家自然科学基金(41971380), 中科院一区, 7.099Q1.

不是样式坏了，是库里的数据脏了。`zot_scan_dirty.py` 扫这些字段，命中下列任一
特征就判脏：

- 字面量：`基金项目` `基金号` `ORCID` `姓名` `单位` `文献网站` `参考文献数量`
  `中科院` `中国科学院` `影响因子` `ＳＳＣＩ` `一区`～`四区` `TOP` `【`
- 正则：`\d+\.\d{2,4}\s*Q[1-4]`（`7.099Q1` 这种）、`Q[1-4][^A-Za-z]`

扫描的字段：`series` `seriesTitle` `extra` `archive` `archiveLocation`
`callNumber` `rights` `libraryCatalog` `shortTitle`。

`zot_clean_dirty.py` 删掉这些字段（只删字段，不删条目），并且：
Zotero 必须关 → 自动 `zotero.sqlite.bak-<时间戳>` 备份 → 单事务，出错回滚 →
顺带 bump `version` 和 `clientDateModified`，同步账号不会丢改动。

回滚：`copy /Y "<数据目录>\zotero.sqlite.bak-xxx" "<数据目录>\zotero.sqlite"`（Zotero 关着）。

## 4. docx 字段结构

每处引用是一个 Word 复杂字段，五个 run：

```
w:fldChar begin → w:instrText → w:fldChar separate → w:t 显示文本 → w:fldChar end
```

`instrText` 内容：

```
 ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"...","properties":{...},
   "citationItems":[{"id":<itemID>,"uris":["http://zotero.org/users/local/.../items/XXXX"],
   "itemData":{<完整 CSL JSON>}}],"schema":"..."} RND <随机串>
```

参考文献占位符是同样的结构，instr 为
`ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY`。

`itemData` 塞完整 CSL 是必要的：Zotero 在还没做库查找之前就靠它渲染显示文本。
`RND` 后面的随机串让 Word 把相邻两个字段当成不同字段，不会合并。

`verify_docx.py` 就是把这些从 `word/document.xml` 里抠出来逐项核对。

## 5. 自动导入为什么不需要 Better BibTeX

Zotero 7/8 的标准 connector（本地 23119 端口）自带
`POST /connector/import`，接受 raw `.bib`，返回新建条目的 itemKey 列表。
必须带的头：`Content-Type: application/x-bibtex` 和 `Zotero-Allowed-Request: true`，
URL 上要带一个唯一的 `?session=`（复用会 409）。

⚠️ 一个真实的坑：如果机器上设了 `HTTP_PROXY` / `HTTPS_PROXY`（VPN、clash 之类），
`urllib` 会把 `127.0.0.1:23119` 也走代理，代理返回 502，看起来就像
"Zotero 没开"。`zot_env.local_opener()` 用 `ProxyHandler({})` 绕开，
所有连接 connector 的地方都必须走它。

装 Better BibTeX 只有两个额外好处：自动按统一规则重生成 citation key；
用 pin 机制把 key 钉死防漂移。对这套管线都不是必需。
