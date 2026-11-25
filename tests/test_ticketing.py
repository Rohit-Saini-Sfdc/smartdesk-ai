"""
Unit and Integration Tests for SmartDesk AI Ticketing Service.
Tests SQLite storage, GitHub adapter logic, failover mechanics, and facade routing.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from src.ticketing.models import (
    TicketCategory,
    TicketCreateRequest,
    TicketPriority,
    TicketResponse,
    TicketStatus,
)
from src.ticketing.sqlite_backend import SQLiteBackend
from src.ticketing.github_backend import GitHubBackend
from src.ticketing.service import TicketingService


@pytest.fixture
def temp_sqlite_backend():
    """Provides a fresh isolated SQLite database instance for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    backend = SQLiteBackend(db_path=temp_path)
    yield backend
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_sqlite_seed_tickets(temp_sqlite_backend):
    """Verify seeded sample tickets exist and match specification."""
    jane_tickets = temp_sqlite_backend.get_tickets_by_email("jane.doe@novatech.com")
    assert len(jane_tickets) >= 1
    t = jane_tickets[0]
    assert t.ticket_id == "IT-2847"
    assert t.status == TicketStatus.IN_PROGRESS.value
    assert len(t.comments) >= 1
    assert "Dell UltraSharp" in t.comments[0].comment

    alex_tickets = temp_sqlite_backend.get_tickets_by_email("alex.smith@novatech.com")
    assert len(alex_tickets) >= 1
    assert alex_tickets[0].ticket_id == "HR-1092"
    assert alex_tickets[0].status == TicketStatus.OPEN.value


def test_sqlite_create_and_fetch_ticket(temp_sqlite_backend):
    """Test creating a new ticket and fetching by reference ID."""
    req = TicketCreateRequest(
        employee_email="test.user@novatech.com",
        title="VPN Connection Drops Randomly",
        description="GlobalProtect VPN disconnects every 20 minutes when switching Wi-Fi access points.",
        category=TicketCategory.IT_SUPPORT.value,
        priority=TicketPriority.HIGH.value,
    )
    created = temp_sqlite_backend.create_ticket(req)

    assert created.ticket_id.startswith("IT-")
    assert created.employee_email == "test.user@novatech.com"
    assert created.status == TicketStatus.OPEN.value
    assert created.priority == TicketPriority.HIGH.value

    # Fetch by ID
    fetched = temp_sqlite_backend.get_ticket_by_id(created.ticket_id)
    assert fetched is not None
    assert fetched.ticket_id == created.ticket_id
    assert fetched.title == req.title
    assert fetched.description == req.description


def test_sqlite_add_comment(temp_sqlite_backend):
    """Test adding comments to an existing ticket."""
    tickets = temp_sqlite_backend.get_tickets_by_email("jane.doe@novatech.com")
    ticket_id = tickets[0].ticket_id

    initial_comment_count = len(tickets[0].comments)
    success = temp_sqlite_backend.add_comment(
        ticket_id=ticket_id,
        author="IT Service Desk",
        comment="Courier tracking number is FEDEX-98218392."
    )
    assert success is True

    updated = temp_sqlite_backend.get_ticket_by_id(ticket_id)
    assert len(updated.comments) == initial_comment_count + 1
    assert "FEDEX-98218392" in updated.comments[-1].comment


def test_github_backend_unconfigured():
    """Verify GitHubBackend handles absence of credentials gracefully."""
    backend = GitHubBackend(token="", owner="", repo="")
    assert not backend.is_configured()
    assert not backend.test_connection()
    assert backend.get_ticket_by_id("GH-1") is None
    assert backend.get_tickets_by_email("test@novatech.com") == []
    assert backend.list_all_tickets() == []


def test_github_backend_parsing():
    """Verify GitHubBackend correctly parses issue markdown and metadata comments."""
    backend = GitHubBackend(token="dummy", owner="owner", repo="repo")
    mock_issue = {
        "number": 42,
        "title": "[IT Support] Replacement Laptop Charger",
        "body": (
            '<!-- smartdesk_meta: {"employee_email": "rachel.green@novatech.com", "category": "IT Support", "priority": "High"} -->\n'
            '### SmartDesk AI Support Ticket\n\n'
            '- **Employee Email:** `rachel.green@novatech.com`\n\n'
            '---\n### Description\nForgot 96W USB-C charger in transit.'
        ),
        "state": "open",
        "labels": [{"name": "smartdesk-ticket"}, {"name": "priority:high"}],
        "created_at": "2026-11-25T10:00:00Z",
        "updated_at": "2026-11-25T10:05:00Z",
        "html_url": "https://github.com/owner/repo/issues/42",
    }

    parsed = backend._parse_issue(mock_issue)
    assert parsed.ticket_id == "GH-42"
    assert parsed.employee_email == "rachel.green@novatech.com"
    assert parsed.title == "Replacement Laptop Charger"
    assert parsed.category == "IT Support"
    assert parsed.priority == "High"
    assert parsed.status == TicketStatus.OPEN.value
    assert "Forgot 96W USB-C charger in transit" in parsed.description


def test_ticketing_service_local_flow(temp_sqlite_backend):
    """Test TicketingService operating in standalone SQLite mode."""
    service = TicketingService(sqlite_db_path=str(temp_sqlite_backend.db_path))
    assert not service.is_github_active
    assert "SQLite" in service.get_backend_status()

    # Search existing seed ticket
    t = service.get_ticket_by_id("IT-2847")
    assert t is not None
    assert t.employee_email == "jane.doe@novatech.com"

    # Create ticket via service
    req = TicketCreateRequest(
        employee_email="sam.altman@novatech.com",
        title="Hardware token sync",
        description="YubiKey 5C needs reactivation for SSO.",
        category=TicketCategory.SECURITY.value,
        priority=TicketPriority.MEDIUM.value,
    )
    new_t = service.create_ticket(req)
    assert new_t.ticket_id.startswith("HR-") or new_t.ticket_id.startswith("IT-")

    # List all
    all_tickets = service.list_all_tickets()
    assert len(all_tickets) >= 3


def test_ticketing_service_github_failover(temp_sqlite_backend):
    """Test that TicketingService seamlessly falls back to SQLite if GitHub throws an exception."""
    service = TicketingService(
        github_token="fake_token",
        github_owner="fake_owner",
        github_repo="fake_repo",
        sqlite_db_path=str(temp_sqlite_backend.db_path),
    )

    # Force github to be considered active for the test, but mock create_ticket to raise an error
    service._github_ready = True
    with patch.object(service.github, "create_ticket", side_effect=RuntimeError("GitHub API rate limit exceeded")):
        req = TicketCreateRequest(
            employee_email="failover.user@novatech.com",
            title="Emergency access request",
            description="Urgent production database access required.",
            category=TicketCategory.IT_SUPPORT.value,
            priority=TicketPriority.CRITICAL.value,
        )
        # Should NOT raise, but fall back to SQLite
        ticket = service.create_ticket(req)
        assert ticket is not None
        assert ticket.backend == "sqlite"
        assert ticket.employee_email == "failover.user@novatech.com"
