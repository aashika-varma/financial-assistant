import argparse
from pathlib import Path

from financial_assistant.storage.database import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--migration",
        default="001_market_data.sql",
    )
    args = parser.parse_args()

    if Path(args.migration).name != args.migration:
        raise ValueError("Pass a migration filename, not a path")

    migration = PROJECT_ROOT / "migrations" / args.migration
    migration_sql = migration.read_text(encoding="utf-8")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cursor.execute(
                "SELECT 1 FROM schema_migrations WHERE name = %s",
                (migration.name,),
            )

            if cursor.fetchone():
                print(f"Already applied: {migration.name}")
                return

            cursor.execute(migration_sql)

            cursor.execute(
                "INSERT INTO schema_migrations (name) VALUES (%s)",
                (migration.name,),
            )

    print(f"Applied: {migration.name}")


if __name__ == "__main__":
    main()