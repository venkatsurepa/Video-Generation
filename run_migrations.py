"""Run all SQL migrations in order against the Supabase database."""
import sys
import os
import glob

import psycopg

CONN_STRING = "postgresql://postgres:GarrettIsDumb!%40@db.qflkctgemkwochgkzqzj.supabase.co:5432/postgres"
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "supabase", "migrations")

def main():
    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    if not files:
        print("ERROR: No migration files found")
        sys.exit(1)

    print(f"Found {len(files)} migration files\n")

    conn = psycopg.connect(CONN_STRING, autocommit=True)

    for filepath in files:
        filename = os.path.basename(filepath)
        print(f"--- Running: {filename} ---")
        try:
            sql = open(filepath, encoding="utf-8").read()
            conn.execute(sql)
            print(f"  SUCCESS\n")
        except Exception as e:
            print(f"  FAILED: {e}\n")
            print("STOPPING — fix the error above before continuing.")
            conn.close()
            sys.exit(1)

    # Verification queries
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Tables
    print("\n--- Public tables ---")
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    ).fetchall()
    for r in rows:
        print(f"  {r[0]}")
    print(f"\nTotal public tables: {len(rows)}")

    # Cron jobs
    print("\n--- Cron jobs ---")
    try:
        cron_rows = conn.execute("SELECT jobid, schedule, command FROM cron.job ORDER BY jobid;").fetchall()
        for r in cron_rows:
            print(f"  Job {r[0]}: {r[1]} | {r[2][:80]}...")
        print(f"\nTotal cron jobs: {len(cron_rows)}")
    except Exception as e:
        print(f"  Could not query cron jobs: {e}")

    # RLS
    print("\n--- RLS status ---")
    rls_rows = conn.execute(
        "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    ).fetchall()
    rls_enabled = 0
    for r in rls_rows:
        status = "ENABLED" if r[1] else "disabled"
        if r[1]:
            rls_enabled += 1
        print(f"  {r[0]}: {status}")
    print(f"\nRLS-enabled tables: {rls_enabled}/{len(rls_rows)}")

    # Indexes
    print("\n--- Index count ---")
    idx_count = conn.execute(
        "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';"
    ).fetchone()[0]
    print(f"  Total indexes: {idx_count}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  Tables:      {len(rows)}")
    print(f"  Indexes:     {idx_count}")
    print(f"  RLS-enabled: {rls_enabled}")
    try:
        print(f"  Cron jobs:   {len(cron_rows)}")
    except:
        print(f"  Cron jobs:   N/A")
    print("=" * 60)

    conn.close()

if __name__ == "__main__":
    main()
