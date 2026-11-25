"""
SQLite Local Ticketing Backend for SmartDesk AI.
Provides local relational database storage, seed records, and status lookup.
Acts as a zero-configuration default and automatic failover engine.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import TicketComment, TicketCreateRequest, TicketPriority, TicketResponse, TicketStatus

logger = logging.getLogger(__name__)


class SQLiteBackend:
    """Handles local ticket storage and state transitions via SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.db_path = Path(db_path) if db_path else base_dir / "data" / "tickets.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_sample_tickets()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize relational database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_ref TEXT UNIQUE NOT NULL,
                    employee_email TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    url TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_ref TEXT NOT NULL,
                    author TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_ref) REFERENCES tickets (ticket_ref)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets (employee_email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_ref ON comments (ticket_ref)")
            conn.commit()

    def _seed_sample_tickets(self):
        """Seed pre-populated tickets for immediate testing of status lookup (Flow C)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tickets")
            count = cursor.fetchone()[0]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                # Sample 1: Jane Doe's open monitor ticket (Matching Flow C from specification)
                cursor.execute("""
                    INSERT INTO tickets (ticket_ref, employee_email, title, description, category, priority, status, created_at, updated_at, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "IT-2847",
                    "jane.doe@novatech.com",
                    "Monitor Flickering Issue",
                    "Employee reports external monitor flickering constantly for past two days while on docking station.",
                    "IT Support",
                    "High",
                    TicketStatus.IN_PROGRESS.value,
                    now,
                    now,
                    "http://localhost:8501/?tab=tickets&id=IT-2847"
                ))
                cursor.execute("""
                    INSERT INTO comments (ticket_ref, author, comment, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    "IT-2847",
                    "Marcus Vance (IT Desktop Support)",
                    "Replacement 4K Dell UltraSharp monitor ordered from depot, scheduled delivery by Thursday.",
                    now
                ))

                # Sample 2: Alex Smith's HR parental leave ticket
                cursor.execute("""
                    INSERT INTO tickets (ticket_ref, employee_email, title, description, category, priority, status, created_at, updated_at, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "HR-1092",
                    "alex.smith@novatech.com",
                    "Parental Leave Schedule Approval",
                    "Requesting approval to split 12-week secondary caregiver leave into two 6-week blocks.",
                    "HR Policies",
                    "Medium",
                    TicketStatus.OPEN.value,
                    now,
                    now,
                    "http://localhost:8501/?tab=tickets&id=HR-1092"
                ))
                cursor.execute("""
                    INSERT INTO comments (ticket_ref, author, comment, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    "HR-1092",
                    "Sarah Jenkins (People Partner)",
                    "Reviewing with department head. Awaiting confirmation on project transition dates.",
                    now
                ))

                conn.commit()
                logger.info("Seeded initial sample tickets for jane.doe@novatech.com and alex.smith@novatech.com.")

    def create_ticket(self, req: TicketCreateRequest) -> TicketResponse:
        """Create a new ticket in the SQLite database."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Determine prefix based on category
            prefix = "IT" if "IT" in req.category.upper() else "HR"
            # Get next ID
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM tickets")
            next_id = cursor.fetchone()[0]
            ticket_ref = f"{prefix}-{3000 + next_id}"
            url = f"http://localhost:8501/?tab=tickets&id={ticket_ref}"

            cursor.execute("""
                INSERT INTO tickets (ticket_ref, employee_email, title, description, category, priority, status, created_at, updated_at, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket_ref,
                req.employee_email.lower().strip(),
                req.title.strip(),
                req.description.strip(),
                req.category,
                req.priority,
                TicketStatus.OPEN.value,
                now,
                now,
                url
            ))
            conn.commit()

        return TicketResponse(
            ticket_id=ticket_ref,
            employee_email=req.employee_email.lower().strip(),
            title=req.title,
            description=req.description,
            category=req.category,
            priority=req.priority,
            status=TicketStatus.OPEN.value,
            created_at=now,
            updated_at=now,
            comments=[],
            url=url,
            backend="sqlite"
        )

    def get_tickets_by_email(self, email: str) -> List[TicketResponse]:
        """Fetch all tickets associated with an employee's email address."""
        email_clean = email.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets WHERE LOWER(employee_email) = ? ORDER BY id DESC", (email_clean,))
            rows = cursor.fetchall()
            tickets = []
            for r in rows:
                ticket_ref = r["ticket_ref"]
                cursor.execute("SELECT author, comment, created_at FROM comments WHERE ticket_ref = ? ORDER BY id ASC", (ticket_ref,))
                c_rows = cursor.fetchall()
                comments = [TicketComment(author=c["author"], comment=c["comment"], created_at=c["created_at"]) for c in c_rows]

                tickets.append(TicketResponse(
                    ticket_id=r["ticket_ref"],
                    employee_email=r["employee_email"],
                    title=r["title"],
                    description=r["description"],
                    category=r["category"],
                    priority=r["priority"],
                    status=r["status"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    comments=comments,
                    url=r["url"],
                    backend="sqlite"
                ))
            return tickets

    def get_ticket_by_id(self, ticket_id: str) -> Optional[TicketResponse]:
        """Fetch a specific ticket by reference ID."""
        ticket_clean = ticket_id.upper().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets WHERE UPPER(ticket_ref) = ?", (ticket_clean,))
            r = cursor.fetchone()
            if not r:
                return None

            cursor.execute("SELECT author, comment, created_at FROM comments WHERE ticket_ref = ? ORDER BY id ASC", (ticket_clean,))
            c_rows = cursor.fetchall()
            comments = [TicketComment(author=c["author"], comment=c["comment"], created_at=c["created_at"]) for c in c_rows]

            return TicketResponse(
                ticket_id=r["ticket_ref"],
                employee_email=r["employee_email"],
                title=r["title"],
                description=r["description"],
                category=r["category"],
                priority=r["priority"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                comments=comments,
                url=r["url"],
                backend="sqlite"
            )

    def add_comment(self, ticket_id: str, author: str, comment: str) -> bool:
        """Add a technician comment or update to an existing ticket."""
        now = datetime.now(timezone.utc).isoformat()
        ticket_clean = ticket_id.upper().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tickets WHERE UPPER(ticket_ref) = ?", (ticket_clean,))
            if not cursor.fetchone():
                return False

            cursor.execute("""
                INSERT INTO comments (ticket_ref, author, comment, created_at)
                VALUES (?, ?, ?, ?)
            """, (ticket_clean, author, comment, now))
            cursor.execute("UPDATE tickets SET updated_at = ? WHERE UPPER(ticket_ref) = ?", (now, ticket_clean))
            conn.commit()
            return True

    def list_all_tickets(self) -> List[TicketResponse]:
        """List all tickets across the enterprise for dashboard display."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets ORDER BY id DESC")
            rows = cursor.fetchall()
            tickets = []
            for r in rows:
                ticket_ref = r["ticket_ref"]
                cursor.execute("SELECT author, comment, created_at FROM comments WHERE ticket_ref = ? ORDER BY id ASC", (ticket_ref,))
                comments = [TicketComment(author=c["author"], comment=c["comment"], created_at=c["created_at"]) for c in cursor.fetchall()]
                tickets.append(TicketResponse(
                    ticket_id=r["ticket_ref"],
                    employee_email=r["employee_email"],
                    title=r["title"],
                    description=r["description"],
                    category=r["category"],
                    priority=r["priority"],
                    status=r["status"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    comments=comments,
                    url=r["url"],
                    backend="sqlite"
                ))
            return tickets
