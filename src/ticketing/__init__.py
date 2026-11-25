"""
Ticketing package for SmartDesk AI.
Exports high-level TicketingService, data models, and storage adapters.
"""

from .github_backend import GitHubBackend
from .models import (
    TicketCategory,
    TicketComment,
    TicketCreateRequest,
    TicketPriority,
    TicketResponse,
    TicketStatus,
)
from .service import TicketingService
from .sqlite_backend import SQLiteBackend

__all__ = [
    "TicketingService",
    "SQLiteBackend",
    "GitHubBackend",
    "TicketCreateRequest",
    "TicketResponse",
    "TicketComment",
    "TicketStatus",
    "TicketPriority",
    "TicketCategory",
]
