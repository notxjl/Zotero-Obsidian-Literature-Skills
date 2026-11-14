"""Safely create the three-directory Obsidian literature layout."""
from __future__ import annotations

import argparse
from pathlib import Path

from config import REPO_ROOT

DIRECTORIES = ("indexs", "notes", "templates")
INDEX_PATH = Path("indexs/文献索引.md")
INDEX_TEMPLATE = """---
type: literature-index
updated: ""
---

# 文献索引

## 概览

- 文献总数：0
- 领域数：0

## 最近同步

- 尚未同步。
"""


def initialize(root: Path, config_path: Path | None = None) -> list[str]:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for relative in DIRECTORIES:
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True)
            created.append(f"directory: {target}")
    index = root / INDEX_PATH
    if not index.exists():
        index.write_text(INDEX_TEMPLATE, encoding="utf-8")
        created.append(f"index: {index}")
    destination = config_path or REPO_ROOT / "config.toml"
    if not destination.exists():
        example = (REPO_ROOT / "config.example.toml").read_text(encoding="utf-8")
        destination.write_text(example, encoding="utf-8")
        created.append(f"config: {destination}")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path.cwd(),
        help="current Obsidian project root (defaults to the working directory)",
    )
    parser.add_argument("--config", type=Path, help="global config output (created only when missing)")
    args = parser.parse_args()
    for item in initialize(args.vault_root, args.config):
        print(f"CREATED {item}")
    root = args.vault_root.expanduser().resolve()
    if not (root / "templates/paper-template.md").is_file():
        print(f"WARN: user template not found: {root / 'templates/paper-template.md'}")
    print("PASS: only indexs/, notes/, templates/ and missing defaults were created; existing files were preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
