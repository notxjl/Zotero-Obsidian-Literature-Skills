# Zotero Obsidian Literature Skills

Obsidian 文献库的 Codex Skills。目标流程是：

```text
指定 Zotero 分类
  -> 检查新增/移出文献
  -> 按 templates/paper-template.md 逐篇写笔记
  -> 重建 indexs/文献索引.md
```

仓库保留三个 Skill：

- `zotero-obsidian-workflow`：分类增量同步、逐篇笔记生成和单文件索引维护。
- `zotero-data-fetcher`：只读读取 Zotero 分类、条目、批注、附件和可访问全文。
- `research-vault-literature-retrieval`：从索引和笔记检索，必要时回查 Zotero 原文。

## Obsidian 目录契约

只使用三个顶层目录：

```text
<VAULT_ROOT>/
├── indexs/
│   └── 文献索引.md
├── notes/
│   └── <领域>/
│       └── <论文标题>.md
└── templates/
    └── paper-template.md
```

`templates/paper-template.md` 由用户维护，Skill 不会生成替代模板或覆盖它。新笔记按领域放在 `notes/` 子目录中；索引始终只有一个文件。

## 安装

要求 Python 3.11+。只读 Zotero 工具仅使用 Python 标准库。(已有 conda 环境可以直接使用；`venv` 只是不使用 conda 时的可选做法)。

```powershell
git clone <this-repository>
cd Zotero-Obsidian-Literature-Skills
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python tools/init_vault.py --vault-root "E:\YourObsidianVault"
```

初始化器只创建缺失的 `indexs/`、`notes/`、`templates/`、空白索引和全局 `config.toml`，不会修改已有笔记、模板或索引。`--vault-root` 默认取当前工作目录，因此进入 Obsidian 项目后也可以省略。

编辑仓库根目录的全局 `config.toml`。它只保存一次 Zotero 数据目录，不保存任何 Vault 路径：

```toml
[paths]
zotero_data_dir = "C:/Users/you/Zotero"
```

当前打开的 Obsidian 项目就是 Vault 根目录。工具会从当前工作目录向上寻找包含 `indexs/`、`notes/`、`templates/` 的项目；也可以显式传入 `--vault-root`。Zotero 路径可用 `ZOTERO_DATA_DIR` 覆盖，配置文件路径可用 `OBSIDIAN_LITERATURE_CONFIG` 覆盖。

检查环境：

```powershell
python tools/check_environment.py
```

不在 Obsidian 项目根目录运行时：

```powershell
python tools/check_environment.py --vault-root "E:\YourObsidianVault"
```

## 日常使用

在 Obsidian 项目中对 agent 说明要处理的 Zotero 分类，例如：

```text
请同步 Zotero 分类“dVLM”，先检查新增和移出的文献，
再按 templates/paper-template.md 逐篇生成缺失笔记，
最后更新 indexs/文献索引.md。
```

主流程会在写文件之前报告：

```text
新增：...
移出：...
索引已有但缺少笔记：...
身份或元数据冲突：...
```

默认处理该分类时需要递归子分类，不需要递归时需要明确说“不包含子分类”。

从 Zotero 分类移出的文献默认只从活动索引移除，笔记文件保留。只有明确要求删除笔记时才会删除。

## 索引规则

索引文件固定为 `indexs/文献索引.md`，按领域分成不同章节。每行至少包含：

```text
题名 | 领域 | 作者 | 年份 | 具体会议/期刊 | 任务
文献类型 | DOI | Zotero Key | Zotero 分类 | 笔记
```

详细格式见 [skills/zotero-obsidian-workflow/references/index-schema.md](skills/zotero-obsidian-workflow/references/index-schema.md)。

## Zotero 只读工具

读取一个分类的当前成员和常用元数据：

```powershell
python tools/zotero_collection_snapshot.py --collection "dVLM"
```

包含子分类：

```powershell
python tools/zotero_collection_snapshot.py --collection "dVLM" --include-subcollections
```

读取单篇论文的批注、Notes、PDF 和全文缓存：

```powershell
python tools/zotero_readonly_fetch.py --key ABCD1234
```

两个工具都以 SQLite `mode=ro` 打开 `zotero.sqlite`，不会写入 Zotero。分类名称重复时请改用 Zotero 分类 Key。

## 模板与笔记更新边界

- 新笔记严格复用 `templates/paper-template.md` 的 frontmatter、章节和区块顺序。
- 生成前先判断论文类型；方法、实证、分析、benchmark、survey、理论和系统论文不共用同一套强制字段。
- 已有笔记只补全模板缺口、元数据和真实证据链接，保留用户已经写下的判断、问题与批注。
- 不为缺失的原文、页码、公式或样本量编造内容。
- 空缺必须区分为“原文未涉及”“作者未报告”“当前材料未定位”或“不适用”。
- “分析者评注（非原文）”不得冒充作者观点；“我的评注”只由用户维护，AI 不填写、不改写、不删除。
- 不批量重写未变化笔记；只有用户明确要求时才重写。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试不要求本机存在 Zotero、真实 PDF 或私人 Vault。
