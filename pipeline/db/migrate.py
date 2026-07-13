"""Apply SQL migrations in order. Usage: python pipeline/db/migrate.py"""

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import env  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def main() -> None:
    dsn = env("DATABASE_URL")
    with psycopg.connect(dsn) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        pending = [
            f for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if f.stem not in applied
        ]
        if not pending:
            print("Nothing to apply — schema is up to date.")
            return
        for f in pending:
            print(f"Applying {f.name}…")
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.stem,))
        conn.commit()
        print(f"Applied {len(pending)} migration(s).")


if __name__ == "__main__":
    main()
