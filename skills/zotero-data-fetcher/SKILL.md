---
name: zotero-data-fetcher
description: "只读读取指定 Zotero 条目或分类的元数据、成员关系、标签、批注、Notes、PDF 附件和可访问全文，为 Obsidian 论文笔记生成提供原始材料。适用于按 Zotero Key、标题或分类核对文献身份并取数；不负责写作、索引或 Zotero 写入。"
---

# Zotero Data Fetcher

## 职责

只负责核实 Zotero 条目身份并提取原始材料。不写论文笔记、不更新文献索引、不翻译、不总结、不修改 Zotero。

## 数据源优先级

1. 当前 agent 已连接的 Zotero MCP integration。
2. 本仓库只读工具：

```powershell
# 一个分类的成员和常用元数据
python tools/zotero_collection_snapshot.py --collection "<分类名或 Key>"

# 一篇论文的批注、Notes、PDF 与全文缓存
python tools/zotero_readonly_fetch.py --key "<父条目 Key>"
```

3. 用户提供的 Zotero 导出、附件或已核验全文。

工具优先读取仓库根目录 `config.toml` 中的全局 `zotero_data_dir`，也可传 `--data-dir` 或设置 `ZOTERO_DATA_DIR`。`config.toml` 不保存 Vault 路径；Vault 根目录来自当前 Obsidian 项目。SQLite 始终以只读方式打开。

分类名重复时必须改用分类 Key。标题只用于人工核对；多个条目标题相同或父子附件关系不清时停止并报告冲突。

## 必须核对的字段

尽量返回并保持以下字段名：

```text
zotero_key
item_type
title
authors
year
venue
doi
url
abstract
tags
collections
annotations
notes
attachments
pdf_path
zotero_item
zotero_pdf
```

- `zotero_key` 是父条目 Key。
- `pdf_key` 是 PDF 附件 Key，不能替代父条目 Key。
- `venue` 从出版或会议字段提取，不能猜。
- 路径只在文件真实存在且当前环境可访问时填写。

## 原始材料优先级

生成论文笔记时按以下顺序使用材料：

1. Zotero 元数据和项目字段。
2. 用户自己的 Zotero Notes、高亮和批注。
3. 可访问全文，包括 Zotero fulltext、HTML、PDF 文本或 OCR 结果。
4. 原始 PDF 页面，用于核验公式、表格、图、页码和引语。

批注代表阅读重点，不能代替论文正文。全文缓存只能是辅助材料，不能自动视为完整或正确。

## 输出边界

- 保留原文语言、出处和可追踪身份。
- 明确区分 `metadata_found`、`annotations_found`、`fulltext_found` 和 `pdf_found`。
- 缺失材料写成未访问或未定位，不能推断为不存在。
- 不移动、覆盖或删除 Zotero 附件。
