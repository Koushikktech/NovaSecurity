from __future__ import annotations

import sqlite3
import pytest
from repositories.expenses import ExpenseRepository
from services.search import SearchService
from routes.search import handle_search_request


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY,
            user TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL
        );
    """)
    cursor.execute("INSERT INTO expenses VALUES (1, 'alice', 25.0, 'team lunch');")
    cursor.execute("INSERT INTO expenses VALUES (2, 'bob', 5000.0, 'confidential bonus payment');")
    conn.commit()
    yield conn
    conn.close()


def test_normal_expense_search(test_db):
    """Happy path: Searching for valid expenses returns only the requesting user's records."""
    repo = ExpenseRepository(test_db)
    service = SearchService(repo)
    res = handle_search_request(service, user="alice", query="lunch")

    assert res["count"] == 1
    assert len(res["expenses"]) == 1
    assert res["expenses"][0]["user"] == "alice"
    assert res["expenses"][0]["description"] == "team lunch"


def test_unauthorized_expense_leak(test_db):
    """Regression test: Attack payload attempting to breach tenant isolation and leak Bob's expenses.
    Expected behavior:
    - RED on buggy unparameterized SQL (leaks Bob's record)
    - GREEN once properly parameterized (no unauthorized leak)
    """
    repo = ExpenseRepository(test_db)
    service = SearchService(repo)
    injection_payload = "lunch' OR user='bob' OR '"

    res = handle_search_request(service, user="alice", query=injection_payload)

    # Tenant isolation assertion: Alice should NEVER be able to see Bob's records!
    returned_users = [item["user"] for item in res["expenses"]]
    assert "bob" not in returned_users, f"Security Violation: leaked records for unauthorized user! Items: {res['expenses']}"
    assert len(res["expenses"]) <= 1
