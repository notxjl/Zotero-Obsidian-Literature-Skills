#!/usr/bin/env python3
"""Read one Zotero collection and its top-level items without modifying Zotero."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from config import configured_path, load_config

YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")
VENUE_FIELDS = (
    "publicationTitle",
    "proceedingsTitle",
    "conferenceName",
    "websiteTitle",
    "university",
    "institution",
    "repository",
)


def discover_data_dir() -> Path | None:
    candidates = [Path.home() / "Zotero"]
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            profiles = Path(appdata) / "Zotero" / "Zotero" / "Profiles"
            if profiles.is_dir():
                candidates.extend(path / "zotero" for path in profiles.iterdir() if path.is_dir())
    return next((p.resolve() for p in candidates if (p / "zotero.sqlite").is_file()), None)


def connect_readonly(data_dir: Path) -> sqlite3.Connection:
    db_uri = quote(str(data_dir / "zotero.sqlite").replace("\\", "/"), safe=":/")
    db = sqlite3.connect(f"file:{db_uri}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def item_fields(db: sqlite3.Connection, item_id: int) -> dict[str, str]:
    rows = db.execute(
        """
        SELECT f.fieldName, v.value
        FROM itemData d
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE d.itemID = ?
        """,
        (item_id,),
    )
    return {row["fieldName"]: row["value"] for row in rows}


def item_authors(db: sqlite3.Connection, item_id: int) -> list[str]:
    try:
        rows = db.execute(
            """
            SELECT c.firstName, c.lastName
            FROM itemCreators ic
            JOIN creators c ON c.creatorID = ic.creatorID
            JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
            WHERE ic.itemID = ? AND ct.creatorType = 'author'
            ORDER BY ic.orderIndex
            """,
            (item_id,),
        )
    except sqlite3.OperationalError:
        rows = db.execute(
            """
            SELECT c.firstName, c.lastName
            FROM itemCreators ic
            JOIN creators c ON c.creatorID = ic.creatorID
            WHERE ic.itemID = ?
            ORDER BY ic.orderIndex
            """,
            (item_id,),
        )
    return [" ".join(filter(None, (row["firstName"], row["lastName"]))) for row in rows]


def item_collections(db: sqlite3.Connection, item_id: int) -> list[str]:
    rows = db.execute(
        """
        SELECT c.collectionName
        FROM collectionItems ci
        JOIN collections c ON c.collectionID = ci.collectionID
        WHERE ci.itemID = ?
        ORDER BY c.collectionName COLLATE NOCASE
        """,
        (item_id,),
    )
    return [row["collectionName"] for row in rows]


def item_tags(db: sqlite3.Connection, item_id: int) -> list[str]:
    rows = db.execute(
        """
        SELECT t.name
        FROM itemTags it
        JOIN tags t ON t.tagID = it.tagID
        WHERE it.itemID = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (item_id,),
    )
    return [row["name"] for row in rows]


def attachment_path(data_dir: Path, pdf_key: str, path_value: str) -> str | None:
    if not path_value:
        return None
    if path_value.startswith("storage:"):
        candidate = data_dir / "storage" / pdf_key / path_value.split(":", 1)[1]
    else:
        candidate = Path(path_value).expanduser()
        if not candidate.is_absolute():
            candidate = data_dir / "storage" / pdf_key / candidate
    candidate = candidate.resolve()
    return str(candidate) if candidate.is_file() else None


def item_attachments(db: sqlite3.Connection, data_dir: Path, item_id: int) -> list[dict[str, object]]:
    rows = db.execute(
        """
        SELECT a.itemID, a.path, a.contentType, i.key AS attachment_key
        FROM itemAttachments a
        JOIN items i ON i.itemID = a.itemID
        WHERE a.parentItemID = ?
        ORDER BY a.itemID
        """,
        (item_id,),
    )
    attachments: list[dict[str, object]] = []
    for row in rows:
        attachment_key = row["attachment_key"]
        storage_dir = data_dir / "storage" / attachment_key
        cache = next((str(path) for path in storage_dir.glob(".zotero-ft-cache*")), None) if storage_dir.is_dir() else None
        annotation_count = 0
        try:
            annotation_count = db.execute(
                "SELECT COUNT(*) FROM itemAnnotations WHERE parentItemID = ?",
                (row["itemID"],),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
        attachments.append(
            {
                "attachment_key": attachment_key,
                "content_type": row["contentType"],
                "path_field": row["path"],
                "pdf_path": attachment_path(data_dir, attachment_key, row["path"] or "")
                if row["contentType"] == "application/pdf"
                else None,
                "fulltext_cache": cache,
                "annotation_count": annotation_count,
            }
        )
    return attachments


def year_from_date(value: str | None) -> str | None:
    match = YEAR.search(value or "")
    return match.group(1) if match else None


def resolve_collection(db: sqlite3.Connection, query: str) -> dict[str, object]:
    rows = db.execute(
        """
        SELECT collectionID, key, collectionName, parentCollectionID
        FROM collections
        WHERE key = ? OR collectionName = ?
        ORDER BY collectionID
        """,
        (query, query),
    ).fetchall()
    if not rows:
        raise LookupError(f"no Zotero collection matched {query!r}")
    if len(rows) != 1:
        choices = ", ".join(f"{row['collectionName']} ({row['key']})" for row in rows)
        raise LookupError(f"{len(rows)} Zotero collections matched {query!r}; use the collection key: {choices}")
    row = rows[0]
    ancestors: list[str] = []
    parent_id = row["parentCollectionID"]
    while parent_id is not None:
        parent = db.execute(
            "SELECT collectionName, parentCollectionID FROM collections WHERE collectionID = ?",
            (parent_id,),
        ).fetchone()
        if parent is None:
            break
        ancestors.append(parent["collectionName"])
        parent_id = parent["parentCollectionID"]
    path = " / ".join(reversed(ancestors + [row["collectionName"]]))
    return {
        "collection_id": row["collectionID"],
        "key": row["key"],
        "name": row["collectionName"],
        "path": path,
    }


def collection_ids(db: sqlite3.Connection, collection_id: int, include_subcollections: bool) -> list[int]:
    if not include_subcollections:
        return [collection_id]
    rows = db.execute(
        """
        WITH RECURSIVE tree(collectionID) AS (
            SELECT ?
            UNION ALL
            SELECT c.collectionID
            FROM collections c
            JOIN tree t ON c.parentCollectionID = t.collectionID
        )
        SELECT collectionID FROM tree
        """,
        (collection_id,),
    )
    return [row["collectionID"] for row in rows]


def collection_items(db: sqlite3.Connection, data_dir: Path, ids: list[int]) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"""
        SELECT DISTINCT i.itemID, i.key, it.typeName
        FROM collectionItems ci
        JOIN items i ON i.itemID = ci.itemID
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        WHERE ci.collectionID IN ({placeholders})
          AND it.typeName NOT IN ('attachment', 'note', 'annotation')
        ORDER BY i.itemID
        """,
        ids,
    ).fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        values = item_fields(db, row["itemID"])
        attachments = item_attachments(db, data_dir, row["itemID"])
        pdfs = [item for item in attachments if item["content_type"] == "application/pdf"]
        primary_pdf = pdfs[0] if pdfs else {}
        notes_count = 0
        try:
            notes_count = db.execute(
                "SELECT COUNT(*) FROM itemNotes WHERE parentItemID = ?",
                (row["itemID"],),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
        zotero_key = row["key"]
        items.append(
            {
                "zotero_key": zotero_key,
                "item_type": row["typeName"],
                "title": values.get("title", ""),
                "authors": item_authors(db, row["itemID"]),
                "year": year_from_date(values.get("date")),
                "venue": next((values[field] for field in VENUE_FIELDS if values.get(field)), ""),
                "doi": values.get("DOI", ""),
                "url": values.get("url", ""),
                "abstract": values.get("abstractNote", ""),
                "tags": item_tags(db, row["itemID"]),
                "collections": item_collections(db, row["itemID"]),
                "attachments": attachments,
                "pdf_key": primary_pdf.get("attachment_key"),
                "pdf_path": primary_pdf.get("pdf_path"),
                "fulltext_cache": primary_pdf.get("fulltext_cache"),
                "notes_count": notes_count,
                "zotero_item": f"zotero://select/library/items/{zotero_key}",
                "zotero_pdf": f"zotero://open-pdf/library/items/{primary_pdf['attachment_key']}" if primary_pdf else None,
            }
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True, help="exact Zotero collection name or collection key")
    parser.add_argument("--data-dir", type=Path, help="Zotero data directory; defaults to platform discovery")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--include-subcollections", action="store_true", help="include child collections recursively")
    args = parser.parse_args()
    config = load_config(args.config)
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else configured_path("zotero_data_dir", config) or discover_data_dir()
    if data_dir is None or not (data_dir / "zotero.sqlite").is_file():
        print("FAIL: zotero.sqlite not found; pass --data-dir or set ZOTERO_DATA_DIR", file=sys.stderr)
        return 2
    db: sqlite3.Connection | None = None
    try:
        db = connect_readonly(data_dir)
        collection = resolve_collection(db, args.collection)
        ids = collection_ids(db, int(collection["collection_id"]), args.include_subcollections)
        items = collection_items(db, data_dir, ids)
        collection.pop("collection_id", None)
        collection["include_subcollections"] = args.include_subcollections
        print(
            json.dumps(
                {
                    "collection": collection,
                    "item_count": len(items),
                    "items": items,
                    "database_access": "read-only SQLite; no writes performed",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except LookupError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except sqlite3.OperationalError as exc:
        print(f"FAIL: Zotero database could not be read (it may be locked or mid-upgrade): {exc}", file=sys.stderr)
        return 2
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
