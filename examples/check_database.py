from financial_assistant.storage.database import get_connection


def main() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

    if result != (1,):
        raise RuntimeError("Unexpected database response")

    print("Neon PostgreSQL connection successful")


if __name__ == "__main__":
    main()