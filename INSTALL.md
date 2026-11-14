# Installation

See the full instructions in [README.md](README.md).

Short Windows setup:

```powershell
git clone <this-repository>
cd Zotero-Obsidian-Literature-Skills
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python tools/init_vault.py --vault-root "E:\YourObsidianVault"
```

Then edit the repository-level `config.toml` once to set `zotero_data_dir`, and add your own `templates/paper-template.md` in the Obsidian project. The config does not store a Vault path.
