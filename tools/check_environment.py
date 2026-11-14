"""Read-only environment diagnostics for the Obsidian literature workflow."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from config import configured_path, load_config, resolve_config_path, resolve_vault_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--vault-root",
        type=Path,
        help="current Obsidian project root (defaults to the nearest project from the working directory)",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    failures = 0

    def report(level: str, label: str, detail: str) -> None:
        nonlocal failures
        print(f"{level}: {label}: {detail}")
        failures += level == "FAIL"

    report(
        "PASS" if sys.version_info >= (3, 11) else "FAIL",
        "Python",
        sys.version.split()[0] + (" (3.11+ required)" if sys.version_info < (3, 11) else ""),
    )
    config_path = resolve_config_path(args.config)
    report("PASS" if config_path.is_file() else "WARN", "config", f"{config_path} " + ("found" if config_path.is_file() else "not found; copy config.example.toml"))
    vault = resolve_vault_root(args.vault_root)
    report("PASS" if vault.is_dir() else "FAIL", "vault_root", str(vault))
    for relative in ("indexs", "notes", "templates"):
        path = vault / relative
        report("PASS" if path.is_dir() else "FAIL", relative, "present" if path.is_dir() else f"missing under {vault}; run tools/init_vault.py")
    for relative in ("indexs/文献索引.md", "templates/paper-template.md"):
        path = vault / relative
        report("PASS" if path.is_file() else "WARN", relative, "present" if path.is_file() else "missing; add your own file")
    zotero = configured_path("zotero_data_dir", config)
    report("PASS" if zotero and (zotero / "zotero.sqlite").is_file() else "WARN", "Zotero data", str(zotero) if zotero else "not configured or not detected")
    report("PASS" if shutil.which("rg") else "WARN", "ripgrep", shutil.which("rg") or "not found; built-in file search remains usable")
    repo = Path(__file__).resolve().parents[1]
    for relative in ("tools/zotero_readonly_fetch.py", "tools/zotero_collection_snapshot.py"):
        path = repo / relative
        report("PASS" if path.is_file() else "FAIL", f"required tool {relative}", "present" if path.is_file() else "missing")
    report("PASS", "Python packages", "all bundled diagnostics use the Python standard library")
    print(f"RESULT: {'FAIL' if failures else 'PASS'} ({failures} failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
