import psycopg

from src.config import get_settings

s = get_settings()
with psycopg.connect(s.database.db_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_schema(), current_user, version()")
        print("CONN:", cur.fetchone())

        cur.execute("SHOW search_path")
        print("SEARCH_PATH:", cur.fetchone())

        cur.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema' ORDER BY nspname")
        print("SCHEMAS:", [r[0] for r in cur.fetchall()])

        cur.execute("SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'travel_advisories'")
        rows = cur.fetchall()
        print("TRAVEL_ADVISORIES (pg_class):", rows if rows else "NOT FOUND IN ANY SCHEMA")

        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 't%' ORDER BY table_name")
        print("PUBLIC TABLES STARTING WITH t:", [r[0] for r in cur.fetchall()])

        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
        print("TOTAL PUBLIC TABLES:", cur.fetchone()[0])
