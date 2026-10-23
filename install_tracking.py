import os

import psycopg


TABLE_NAME = "sora_personal_install_users"


class DatabaseNotConfiguredError(RuntimeError):
    pass


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")
    return database_url


def ensure_tracking_table(cursor: psycopg.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            user_id TEXT PRIMARY KEY
        )
        """
    )


def record_personal_install_user(user_id: str) -> None:
    if not user_id.isdecimal():
        raise ValueError("Personal-install user ID must be numeric")

    with psycopg.connect(get_database_url()) as connection:
        with connection.cursor() as cursor:
            ensure_tracking_table(cursor)
            cursor.execute(
                f"""
                INSERT INTO {TABLE_NAME} (user_id)
                VALUES (%s)
                ON CONFLICT (user_id)
                DO NOTHING
                """,
                (user_id,),
            )


def list_personal_install_users() -> list[str]:
    with psycopg.connect(get_database_url()) as connection:
        with connection.cursor() as cursor:
            ensure_tracking_table(cursor)
            cursor.execute(
                f"""
                SELECT user_id
                FROM {TABLE_NAME}
                ORDER BY user_id
                """
            )
            return [row[0] for row in cursor.fetchall()]
