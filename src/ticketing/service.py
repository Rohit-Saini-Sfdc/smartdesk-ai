"""
Ticketing Service Facade for SmartDesk AI.
Orchestrates dual-backend ticketing operations with GitHub Issues and local SQLite fallback.
Provides resilient operations, cross-backend search, and automated failover.
"""

import logging
from typing import List, Optional

from .github_backend import GitHubBackend
from .models import (
    TicketCategory,
    TicketComment,
    TicketCreateRequest,
    TicketPriority,
    TicketResponse,
    TicketStatus,
)
from .sqlite_backend import SQLiteBackend

logger = logging.getLogger(__name__)


class TicketingService:
    """Enterprise ticketing adapter supporting GitHub Issues REST API with automatic SQLite fallback."""

    def __init__(
        self,
        github_token: Optional[str] = None,
        github_owner: Optional[str] = None,
        github_repo: Optional[str] = None,
        sqlite_db_path: Optional[str] = None,
    ):
        self.sqlite = SQLiteBackend(db_path=sqlite_db_path)
        self.github = GitHubBackend(
            token=github_token,
            owner=github_owner,
            repo=github_repo,
        )

        self._github_ready = False
        if self.github.is_configured():
            try:
                self._github_ready = self.github.test_connection()
                if self._github_ready:
                    logger.info("TicketingService: GitHub Issues backend connected successfully.")
                else:
                    logger.warning("TicketingService: GitHub credentials provided but connection test failed. Using SQLite fallback.")
            except Exception as e:
                logger.warning(f"TicketingService: Error connecting to GitHub backend: {e}. Using SQLite fallback.")
        else:
            logger.info("TicketingService: Running in zero-dependency local mode using SQLite backend.")

    @property
    def is_github_active(self) -> bool:
        return self._github_ready and self.github.is_configured()

    def get_backend_status(self) -> str:
        """Returns readable description of active backend."""
        if self.is_github_active:
            return f"GitHub Issues ({self.github.owner}/{self.github.repo}) + Local SQLite Fallback"
        return "Local SQLite Relational Database (Standalone)"

    def create_ticket(self, req: TicketCreateRequest) -> TicketResponse:
        """
        Creates a new support ticket.
        Attempts creation via GitHub Issues if active; automatically fails over to SQLite on any exception.
        """
        if self.is_github_active:
            try:
                ticket = self.github.create_ticket(req)
                logger.info(f"Created ticket on GitHub Issues: {ticket.ticket_id}")
                return ticket
            except Exception as e:
                logger.error(f"Failed to create ticket on GitHub Issues: {e}. Falling back to SQLite.")

        # SQLite fallback / default
        ticket = self.sqlite.create_ticket(req)
        logger.info(f"Created ticket in SQLite: {ticket.ticket_id}")
        return ticket

    def get_tickets_by_email(self, email: str) -> List[TicketResponse]:
        """
        Searches all tickets submitted by an employee across both GitHub and SQLite backends.
        Aggregates results and sorts by most recent.
        """
        results: List[TicketResponse] = []
        seen_ids = set()

        # Query SQLite
        try:
            sqlite_tickets = self.sqlite.get_tickets_by_email(email)
            for t in sqlite_tickets:
                if t.ticket_id not in seen_ids:
                    results.append(t)
                    seen_ids.add(t.ticket_id)
        except Exception as e:
            logger.error(f"Error querying SQLite for tickets by email: {e}")

        # Query GitHub if configured
        if self.github.is_configured():
            try:
                gh_tickets = self.github.get_tickets_by_email(email)
                for t in gh_tickets:
                    if t.ticket_id not in seen_ids:
                        results.append(t)
                        seen_ids.add(t.ticket_id)
            except Exception as e:
                logger.warning(f"Error querying GitHub for tickets by email: {e}")

        results.sort(key=lambda x: x.created_at, reverse=True)
        return results

    def get_ticket_by_id(self, ticket_id: str) -> Optional[TicketResponse]:
        """
        Fetches ticket details by reference ID (e.g. 'IT-2847', 'HR-1092', 'GH-14', '#14', '14').
        Intelligently routes based on identifier prefix.
        """
        clean_id = ticket_id.strip()

        # If reference begins with GH or is purely numeric, check GitHub first
        if clean_id.upper().startswith("GH-") or clean_id.startswith("#") or clean_id.isdigit():
            if self.github.is_configured():
                res = self.github.get_ticket_by_id(clean_id)
                if res:
                    return res
            # Fallback to SQLite
            return self.sqlite.get_ticket_by_id(clean_id)

        # Standard IT- / HR- format: check SQLite first
        res = self.sqlite.get_ticket_by_id(clean_id)
        if res:
            return res

        # Fallback to GitHub
        if self.github.is_configured():
            return self.github.get_ticket_by_id(clean_id)

        return None

    def add_comment(self, ticket_id: str, author: str, comment: str) -> bool:
        """
        Appends an internal note or agent comment to the specified ticket.
        """
        clean_id = ticket_id.strip()
        if clean_id.upper().startswith("GH-") or clean_id.startswith("#") or clean_id.isdigit():
            if self.github.is_configured() and self.github.add_comment(clean_id, author, comment):
                return True
            return self.sqlite.add_comment(clean_id, author, comment)

        # Try SQLite first
        if self.sqlite.add_comment(clean_id, author, comment):
            return True

        if self.github.is_configured():
            return self.github.add_comment(clean_id, author, comment)

        return False

    def list_all_tickets(self, limit: int = 50) -> List[TicketResponse]:
        """
        Aggregates all tickets from SQLite and GitHub for unified administrative overview.
        """
        results: List[TicketResponse] = []
        seen_ids = set()

        # Fetch from SQLite
        try:
            for t in self.sqlite.list_all_tickets():
                if t.ticket_id not in seen_ids:
                    results.append(t)
                    seen_ids.add(t.ticket_id)
        except Exception as e:
            logger.error(f"Error listing SQLite tickets: {e}")

        # Fetch from GitHub if active
        if self.github.is_configured():
            try:
                for t in self.github.list_all_tickets(limit=limit):
                    if t.ticket_id not in seen_ids:
                        results.append(t)
                        seen_ids.add(t.ticket_id)
            except Exception as e:
                logger.warning(f"Error listing GitHub tickets: {e}")

        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]
