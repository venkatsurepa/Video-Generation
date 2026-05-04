"""Introspect travel-safety related tables to verify schema before model writing."""
from __future__ import annotations

import json
import sys

import psycopg

from src.config import get_settings

TABLES = ["travel_advisories", "video_destinations", "partner_app_metrics", "channels"]


def main() -> int:
    settings = get_settings()
    dsn = settings.database.db_url
    if not dsn:
        print("ERROR: SUPABASE_DB_URL not set", file=sys.stderr)
        return 1

    out: dict[str, list[dict[str, object]]] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for tbl in TABLES:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (tbl,),
            )
            cols = [
                {
                    "column_name": r[0],
                    "data_type": r[1],
                    "is_nullable": r[2],
                    "column_default": r[3],
                }
                for r in cur.fetchall()
            ]
            out[tbl] = cols

            # Constraints
            cur.execute(
                """
                SELECT con.conname, pg_get_constraintdef(con.oid)
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = 'public' AND rel.relname = %s
                ORDER BY con.conname
                """,
                (tbl,),
            )
            cons = [{"name": r[0], "def": r[1]} for r in cur.fetchall()]
            out[f"{tbl}__constraints"] = cons

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
