from __future__ import annotations

import sqlite3
from typing import Any


class ExpenseRepository:
    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn

    def search_user_expenses(self, user: str, query: str) -> list[dict[str, Any]]:
        """Search expenses for a specific user matching the query string.
        Vulnerability: String interpolation allows SQL injection to bypass user isolation!
        """
        cursor = self.conn.cursor()
        # VULNERABLE: Direct f-string interpolation into SQL statement
        sql = f"SELECT id, user, amount, description FROM expenses WHERE user = '{user}' AND description LIKE '%{query}%'"
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [
            {"id": r[0], "user": r[1], "amount": r[2], "description": r[3]}
            for r in rows
        ]
