"""Shared helpers for the public API."""
import math
from typing import Any, Dict, List, Optional

from fastapi import Query


class PaginationParams:
    """Dependency for pagination query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.per_page = per_page
        self.offset = (page - 1) * per_page


def paginated_response(
    items: List[Any],
    total: int,
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    """Wrap a list of items in the standard paginated response format."""
    return {
        "data": items,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": math.ceil(total / per_page) if per_page else 0,
        },
    }


def single_response(data: Any) -> Dict[str, Any]:
    """Wrap a single item in the standard response format."""
    return {"data": data}


def error_response(code: str, message: str) -> Dict[str, Any]:
    """Build a standard error response body."""
    return {"error": {"code": code, "message": message}}
