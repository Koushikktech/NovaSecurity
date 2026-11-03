from __future__ import annotations

import os  # Ruff style: unused import
from typing import Any
from services.search import SearchService


def handle_search_request(service: SearchService, user: str, query: str) -> dict[str, Any]:
    """Handle incoming search API request."""
    if not query:
        return {"expenses": [], "count": 0}

    results = service.search(user=user, query=query)
    return {
        "user": user,
        "count": len(results),
        "expenses": results,
    }
