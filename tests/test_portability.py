from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from config import discover_vault_root, load_config, resolve_vault_root
from init_vault import INDEX_PATH, initialize


class PortabilityTests(unittest.TestCase):
    def test_config_example_loads_and_requires_no_packages(self):
        import tomllib

        with (ROOT / "config.example.toml").open("rb") as stream:
            data = tomllib.load(stream)
        self.assertEqual(set(data["paths"]), {"zotero_data_dir"})

    def test_loader_ignores_legacy_vault_root(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "legacy.toml"
            config.write_text(
                '[paths]\nvault_root = "E:/legacy-vault"\nzotero_data_dir = "C:/Users/example/Zotero"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                load_config(config),
                {"zotero_data_dir": "C:/Users/example/Zotero"},
            )

    def test_initializer_is_idempotent_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            vault, config = base / "obsidian-vault", base / "local-config.toml"
            (vault / "templates").mkdir(parents=True)
            template = vault / "templates/paper-template.md"
            template.write_text("user template", encoding="utf-8")
            index = vault / INDEX_PATH
            index.parent.mkdir(parents=True)
            index.write_text("user index", encoding="utf-8")

            first = initialize(vault, config)
            self.assertEqual(template.read_text(encoding="utf-8"), "user template")
            self.assertEqual(index.read_text(encoding="utf-8"), "user index")
            self.assertTrue((vault / "indexs").is_dir())
            self.assertTrue((vault / "notes").is_dir())
            self.assertTrue((vault / "templates").is_dir())
            self.assertTrue(config.is_file())
            self.assertNotIn("vault_root", config.read_text(encoding="utf-8"))
            self.assertTrue(first)
            self.assertEqual(initialize(vault, config), [])

    def test_environment_checker_cli_on_initialized_arbitrary_root(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            vault, config = base / "obsidian-root", base / "config.toml"
            initialize(vault, config)
            (vault / "templates/paper-template.md").write_text("template", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/check_environment.py"),
                    "--config",
                    str(config),
                    "--vault-root",
                    str(vault),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: vault_root", result.stdout)
            self.assertIn("PASS: templates/paper-template.md", result.stdout)
            self.assertIn("RESULT: PASS", result.stdout)

    def test_vault_root_uses_current_project_and_not_global_config(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            vault = base / "obsidian-vault"
            nested = vault / "notes/领域"
            nested.mkdir(parents=True)
            for relative in ("indexs", "templates"):
                (vault / relative).mkdir()
            self.assertEqual(discover_vault_root(nested), vault.resolve())
            self.assertEqual(discover_vault_root(base), base.resolve())
            other = base / "explicit-vault"
            self.assertEqual(resolve_vault_root(other, start=nested), other.resolve())

    def test_required_repository_paths_exist_and_old_pipeline_is_removed(self):
        required = (
            "tools/zotero_collection_snapshot.py",
            "tools/zotero_readonly_fetch.py",
            "tools/check_environment.py",
            "tools/init_vault.py",
            "skills/zotero-obsidian-workflow/SKILL.md",
            "skills/zotero-data-fetcher/SKILL.md",
            "skills/research-vault-literature-retrieval/SKILL.md",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)
        removed = (
            "skills/zotero-fulltext-archiver",
            "skills/zotero-analytical-writer",
            "skills/zotero-collection-manager",
            "skills/research-vault-knowledge-maintainer",
            "skills/research-vault-ingest-orchestrator",
            "tools/run_mineru_production.py",
        )
        for relative in removed:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_paper_template_preserves_evidence_and_user_comment_boundaries(self):
        template = (ROOT / "templates/paper-template.md").read_text(encoding="utf-8")
        for token in (
            "primary_paper_type:",
            "content_status:",
            "zotero_key:",
            "原文未涉及",
            "作者未报告",
            "当前材料未定位",
            "不适用",
            "分析者评注（非原文）",
            "## 12. 我的评注",
        ):
            self.assertIn(token, template)
        self.assertNotIn("#### 模块/算法 B", template)
        user_comment = template.split("## 12. 我的评注", 1)[1]
        self.assertIn("AI 不得填写", user_comment)

    def test_only_three_public_skill_names_remain(self):
        names = []
        for path in (ROOT / "skills").glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", text)
            self.assertIsNotNone(match, path)
            names.append(match.group(1))
        self.assertEqual(
            set(names),
            {
                "zotero-obsidian-workflow",
                "zotero-data-fetcher",
                "research-vault-literature-retrieval",
            },
        )

    def test_skill_ui_names_are_english(self):
        for path in (ROOT / "skills").glob("*/agents/openai.yaml"):
            text = path.read_text(encoding="utf-8")
            for field in ("display_name", "short_description"):
                match = re.search(rf'(?m)^\s*{field}:\s*"([^"]+)"\s*$', text)
                self.assertIsNotNone(match, f"{path}: missing {field}")
                self.assertTrue(match.group(1).isascii(), f"{path}: {field} must use English")

    def test_no_machine_specific_paths_in_runtime_or_skills(self):
        forbidden = re.compile(r"(?i)(?:D:|C:)\\(?:ResearchVault(?:_Archive)?|research|MinerU)(?:\\|\b)")
        paths = list((ROOT / "tools").rglob("*.py")) + list((ROOT / "skills").rglob("SKILL.md"))
        for path in paths:
            self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), str(path))

    def test_internal_markdown_file_links_resolve(self):
        link_re = re.compile(r"\]\(([^)]+)\)")
        for path in list(ROOT.rglob("*.md")):
            if ".git" in path.parts:
                continue
            for target in link_re.findall(path.read_text(encoding="utf-8")):
                if re.match(r"^[a-z]+://", target, re.I) or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0]
                if not clean or clean == "this-repository":
                    continue
                resolved = (path.parent / clean).resolve()
                self.assertTrue(resolved.exists(), f"{path.relative_to(ROOT)} -> {target}")

    def test_skill_reference_paths_exist(self):
        file_ref = re.compile(r"(?:references|scripts|tools)/[A-Za-z0-9_./\-\u4e00-\u9fff]+(?:\.md|\.py|\.yaml|\.yml|/)")
        for path in list(ROOT.rglob("*.md")) + list(ROOT.rglob("*.yaml")) + list(ROOT.rglob("*.yml")):
            if ".git" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for found in file_ref.findall(text):
                relative = found.rstrip("/")
                if "<" in relative or relative.endswith("..."):
                    continue
                resolved = (path.parent / relative).resolve()
                root_resolved = (ROOT / relative).resolve()
                nested_match = next(ROOT.rglob(relative), None)
                if not (resolved.exists() or root_resolved.exists() or nested_match):
                    self.fail(f"missing referenced file: {path.relative_to(ROOT)} -> {relative}")

    def test_zotero_collection_snapshot_reads_exact_and_nested_collections_read_only(self):
        import zotero_collection_snapshot as snapshot

        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            storage = data / "storage/PDFKEY1"
            storage.mkdir(parents=True)
            (storage / "paper.pdf").write_bytes(b"%PDF-fixture")
            (storage / ".zotero-ft-cache").write_text("cached text", encoding="utf-8")
            db_path = data / "zotero.sqlite"
            db = sqlite3.connect(db_path)
            db.executescript(
                """
                CREATE TABLE collections(
                    collectionID INTEGER PRIMARY KEY,
                    collectionName TEXT,
                    parentCollectionID INTEGER,
                    key TEXT
                );
                CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT, itemTypeID INTEGER);
                CREATE TABLE itemTypes(itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
                CREATE TABLE fields(fieldID INTEGER PRIMARY KEY, fieldName TEXT);
                CREATE TABLE itemData(itemID INTEGER, fieldID INTEGER, valueID INTEGER);
                CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY, value TEXT);
                CREATE TABLE creators(creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
                CREATE TABLE creatorTypes(creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
                CREATE TABLE itemCreators(itemID INTEGER, creatorID INTEGER, creatorTypeID INTEGER, orderIndex INTEGER);
                CREATE TABLE collectionItems(collectionID INTEGER, itemID INTEGER);
                CREATE TABLE tags(tagID INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE itemTags(itemID INTEGER, tagID INTEGER);
                CREATE TABLE itemAttachments(itemID INTEGER, parentItemID INTEGER, path TEXT, contentType TEXT);
                CREATE TABLE itemAnnotations(itemID INTEGER, parentItemID INTEGER);
                CREATE TABLE itemNotes(itemID INTEGER, parentItemID INTEGER, note TEXT);
                """
            )
            db.executemany(
                "INSERT INTO itemTypes VALUES (?, ?)",
                [(1, "journalArticle"), (2, "attachment")],
            )
            db.executemany(
                "INSERT INTO collections VALUES (?, ?, ?, ?)",
                [(1, "创新经济地理", None, "COLL1"), (2, "子分类", 1, "COLL2")],
            )
            db.executemany(
                "INSERT INTO items VALUES (?, ?, ?)",
                [(1, "PARENT1", 1), (2, "PDFKEY1", 2), (3, "CHILD1", 1)],
            )
            db.executemany(
                "INSERT INTO collectionItems VALUES (?, ?)",
                [(1, 1), (2, 3)],
            )
            db.executemany(
                "INSERT INTO fields VALUES (?, ?)",
                [(1, "title"), (2, "date"), (3, "DOI"), (4, "publicationTitle"), (5, "abstractNote"), (6, "url")],
            )
            db.executemany(
                "INSERT INTO itemDataValues VALUES (?, ?)",
                [
                    (1, "Portable Research"),
                    (2, "2024-01-01"),
                    (3, "10.1234/example"),
                    (4, "Journal of Portable Tests"),
                    (5, "Abstract"),
                    (6, "https://example.test"),
                    (7, "Child Research"),
                ],
            )
            db.executemany(
                "INSERT INTO itemData VALUES (?, ?, ?)",
                [(1, 1, 1), (1, 2, 2), (1, 3, 3), (1, 4, 4), (1, 5, 5), (1, 6, 6), (3, 1, 7)],
            )
            db.execute("INSERT INTO creators VALUES (1, 'Ada', 'Lovelace')")
            db.execute("INSERT INTO creatorTypes VALUES (1, 'author')")
            db.execute("INSERT INTO itemCreators VALUES (1, 1, 1, 0)")
            db.execute("INSERT INTO tags VALUES (1, 'urban')")
            db.execute("INSERT INTO itemTags VALUES (1, 1)")
            db.execute("INSERT INTO itemAttachments VALUES (2, 1, 'storage:paper.pdf', 'application/pdf')")
            db.execute("INSERT INTO itemAnnotations VALUES (10, 2)")
            db.execute("INSERT INTO itemNotes VALUES (11, 1, '<p>Research note</p>')")
            db.commit()
            db.close()

            before = hashlib.sha256(db_path.read_bytes()).hexdigest()
            capture = io.StringIO()
            with mock.patch.object(
                sys, "argv", ["snapshot", "--collection", "创新经济地理", "--data-dir", str(data)]
            ), contextlib.redirect_stdout(capture):
                self.assertEqual(snapshot.main(), 0)
            exact = json.loads(capture.getvalue())
            self.assertEqual(exact["collection"]["key"], "COLL1")
            self.assertFalse(exact["collection"]["include_subcollections"])
            self.assertEqual(exact["item_count"], 1)
            item = exact["items"][0]
            self.assertEqual(item["zotero_key"], "PARENT1")
            self.assertEqual(item["venue"], "Journal of Portable Tests")
            self.assertEqual(item["pdf_key"], "PDFKEY1")
            self.assertEqual(item["attachments"][0]["annotation_count"], 1)
            self.assertTrue(item["pdf_path"].endswith("paper.pdf"))

            capture = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                [
                    "snapshot",
                    "--collection",
                    "COLL1",
                    "--data-dir",
                    str(data),
                    "--include-subcollections",
                ],
            ), contextlib.redirect_stdout(capture):
                self.assertEqual(snapshot.main(), 0)
            nested = json.loads(capture.getvalue())
            self.assertEqual(nested["item_count"], 2)
            self.assertEqual({row["zotero_key"] for row in nested["items"]}, {"PARENT1", "CHILD1"})
            self.assertEqual(before, hashlib.sha256(db_path.read_bytes()).hexdigest())

    def test_zotero_fetch_helper_reads_fixture_read_only(self):
        import zotero_readonly_fetch as fetcher

        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            storage = data / "storage/PDFKEY1"
            storage.mkdir(parents=True)
            (storage / "paper.pdf").write_bytes(b"%PDF-fixture")
            (storage / ".zotero-ft-cache").write_text("cached text", encoding="utf-8")
            db_path = data / "zotero.sqlite"
            db = sqlite3.connect(db_path)
            db.executescript(
                """
                CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT, itemTypeID INTEGER);
                CREATE TABLE fields(fieldID INTEGER PRIMARY KEY, fieldName TEXT);
                CREATE TABLE itemData(itemID INTEGER, fieldID INTEGER, valueID INTEGER);
                CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY, value TEXT);
                CREATE TABLE creators(creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
                CREATE TABLE itemCreators(itemID INTEGER, creatorID INTEGER, orderIndex INTEGER);
                CREATE TABLE collections(collectionID INTEGER PRIMARY KEY, collectionName TEXT);
                CREATE TABLE collectionItems(collectionID INTEGER, itemID INTEGER);
                CREATE TABLE itemAttachments(itemID INTEGER, parentItemID INTEGER, path TEXT, contentType TEXT);
                CREATE TABLE itemAnnotations(itemID INTEGER, parentItemID INTEGER, type TEXT, authorName TEXT, comment TEXT, text TEXT, pageLabel TEXT);
                CREATE TABLE itemNotes(itemID INTEGER, parentItemID INTEGER, note TEXT);
                """
            )
            db.execute("INSERT INTO items VALUES (1, 'PARENT1', 1)")
            db.execute("INSERT INTO items VALUES (2, 'PDFKEY1', 2)")
            db.executemany("INSERT INTO fields VALUES (?, ?)", [(1, "title"), (2, "date"), (3, "DOI"), (4, "publicationTitle")])
            db.executemany(
                "INSERT INTO itemDataValues VALUES (?, ?)",
                [(1, "Portable Research"), (2, "2024-01-01"), (3, "10.1234/example"), (4, "Journal")],
            )
            db.executemany("INSERT INTO itemData VALUES (1, ?, ?)", [(1, 1), (2, 2), (3, 3), (4, 4)])
            db.execute("INSERT INTO creators VALUES (1, 'Ada', 'Lovelace')")
            db.execute("INSERT INTO itemCreators VALUES (1, 1, 0)")
            db.execute("INSERT INTO collections VALUES (1, 'Methods')")
            db.execute("INSERT INTO collectionItems VALUES (1, 1)")
            db.execute("INSERT INTO itemAttachments VALUES (2, 1, 'storage:paper.pdf', 'application/pdf')")
            db.execute("INSERT INTO itemAnnotations VALUES (3, 2, 'highlight', 'Ada', '', 'verified text', '2')")
            db.execute("INSERT INTO itemNotes VALUES (4, 1, '<p>Research note</p>')")
            db.commit()
            db.close()

            before = hashlib.sha256(db_path.read_bytes()).hexdigest()
            capture = io.StringIO()
            with mock.patch.object(
                sys, "argv", ["fetch", "--key", "PARENT1", "--data-dir", str(data)]
            ), contextlib.redirect_stdout(capture):
                self.assertEqual(fetcher.main(), 0)
            result = json.loads(capture.getvalue())
            self.assertEqual(result["zotero_key"], "PARENT1")
            self.assertEqual(result["pdf_key"], "PDFKEY1")
            self.assertEqual(result["title"], "Portable Research")
            self.assertEqual(result["venue"], "Journal")
            self.assertEqual(result["annotations"][0]["text"], "verified text")
            self.assertEqual(result["notes"], ["<p>Research note</p>"])
            self.assertEqual(Path(result["pdf_path"]).resolve(), (storage / "paper.pdf").resolve())
            self.assertTrue(result["fulltext_cache"].endswith(".zotero-ft-cache"))
            self.assertEqual(before, hashlib.sha256(db_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
