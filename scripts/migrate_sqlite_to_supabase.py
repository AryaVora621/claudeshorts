"""One-time copy of data/app.db into the Supabase Postgres store.

Usage: python -m scripts.migrate_sqlite_to_supabase [path/to/app.db] [--force]

Reads all rows from the local SQLite file and writes them into the tables
created by claudeshorts.store.db.init_db(), preserving primary key ids so
post_threads foreign keys stay valid. Refuses to run if the destination
already has data, unless --force is passed. Never modifies the source file.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import psycopg

from claudeshorts.store import db

_TABLE_ORDER = ("items", "posts", "threads", "post_threads", "pins", "runs", "jobs")

_SEQUENCE_TABLES = ("items", "posts", "threads", "runs", "jobs")


def _destination_is_empty(conn: psycopg.Connection) -> bool:
    for table in _TABLE_ORDER:
        n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        if n > 0:
            return False
    return True


def _copy_table(sconn: sqlite3.Connection, pconn: psycopg.Connection, table: str) -> int:
    sconn.row_factory = sqlite3.Row
    rows = sconn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    columns = rows[0].keys()
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    for row in rows:
        pconn.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            tuple(row[c] for c in columns),
        )
    return len(rows)


def _reset_sequences(pconn: psycopg.Connection) -> None:
    for table in _SEQUENCE_TABLES:
        pconn.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
            f"(SELECT MAX(id) FROM {table}) IS NOT NULL)"
        )


def main(sqlite_path: Path, *, force: bool = False) -> dict[str, int]:
    db.init_db()
    counts: dict[str, int] = {}
    with db.connect() as pconn:
        if not force and not _destination_is_empty(pconn):
            raise RuntimeError(
                "Destination Supabase tables are non-empty. Pass --force to "
                "proceed anyway, or truncate the tables first if this is a "
                "deliberate re-run."
            )
        sconn = sqlite3.connect(sqlite_path)
        try:
            for table in _TABLE_ORDER:
                counts[table] = _copy_table(sconn, pconn, table)
            _reset_sequences(pconn)
        finally:
            sconn.close()

    sconn = sqlite3.connect(sqlite_path)
    try:
        for table in _TABLE_ORDER:
            source_n = sconn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if source_n != counts[table]:
                raise RuntimeError(
                    f"Row count mismatch for {table}: source had {source_n}, "
                    f"copied {counts[table]}."
                )
    finally:
        sconn.close()

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sqlite_path", nargs="?", default="data/app.db", type=Path,
        help="Path to the source SQLite file (default: data/app.db)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if the destination tables are non-empty",
    )
    args = parser.parse_args()
    result = main(args.sqlite_path, force=args.force)
    for table, n in result.items():
        print(f"{table}: {n} rows copied")
