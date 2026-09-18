---
title: {{TITLE}}
---

%% —— ZotLink 正文语法速查（%% 开头的行不会进 docx）——————————————
%% 引用单篇：  [[cite:key]]
%% 合并引用：  [[cite:key1;key2]]       →  一个 Word 字段，一个括号
%% key 就是 data/references.bib 里 @article{key, ...} 的 key
%% 标题：      # 一级   ## 二级
%% 编号条目：  (1) **粗体引导语**：正文……
%% 参考文献：  [[bibliography: 参考文献 / References]]
%% 同一段内换行自动接续：汉字之间不补空格，汉字接 Latin（引用括号就在这）补空格，遇到中文标点不补；空行分段。
%% ————————————————————————————————————————————————

# 引言

在这里写正文。写完把 BibTeX 条目加进 data/references.bib，在句子里插入引用标记，
然后跑一次管线，就会在 output/ 得到带 Zotero 活动字段的 docx。

[[bibliography: 参考文献 / References]]
