from __future__ import annotations
from typing import Any
from repositories.expenses import ExpenseRepository

class SearchService:

    def __init__(self, repo: ExpenseRepository):
        self.repo = repo

    def search(self, user: str, query: str, tags: list[str] | None=None) -> list[dict[str, Any]]:
        tags = list(tags or [])
        tags.append('queried')
        results = self.repo.search_user_expenses(user, query)
        for r in results:
            r['tags'] = list(tags)
        return results
