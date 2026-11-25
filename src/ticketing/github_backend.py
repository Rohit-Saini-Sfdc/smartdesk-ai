"""
GitHub Issues Ticketing Backend for SmartDesk AI.
Integrates with GitHub REST API (v3) to manage enterprise support tickets as issues.
Provides automatic metadata serialization, comment synchronization, and employee search.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from .models import (
    TicketComment,
    TicketCreateRequest,
    TicketPriority,
    TicketResponse,
    TicketStatus,
)

logger = logging.getLogger(__name__)


class GitHubBackend:
    """Manages support tickets backed by GitHub Issues via REST API."""

    def __init__(
        self,
        token: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.owner = owner or os.getenv("GITHUB_REPO_OWNER", "")
        self.repo = repo or os.getenv("GITHUB_REPO_NAME", "")
        self.api_base = f"https://api.github.com/repos/{self.owner}/{self.repo}" if self.owner and self.repo else ""

    def is_configured(self) -> bool:
        """Check if all required GitHub credentials and repository details are present."""
        return bool(self.token and self.owner and self.repo)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SmartDesk-AI-Agent",
        }

    def test_connection(self) -> bool:
        """Verify repository access and token permissions."""
        if not self.is_configured():
            return False
        try:
            resp = requests.get(self.api_base, headers=self._get_headers(), timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"GitHub connection test failed: {e}")
            return False

    def _build_body(self, req: TicketCreateRequest, timestamp: str) -> str:
        """Format issue body with embedded metadata comment and human-readable markdown."""
        meta = {
            "employee_email": req.employee_email.lower().strip(),
            "category": req.category,
            "priority": req.priority,
            "created_at": timestamp,
        }
        meta_json = json.dumps(meta)

        return (
            f"<!-- smartdesk_meta: {meta_json} -->\n"
            f"### SmartDesk AI Support Ticket\n\n"
            f"- **Employee Email:** `{req.employee_email.lower().strip()}`\n"
            f"- **Department / Category:** {req.category}\n"
            f"- **Urgency / Priority:** {req.priority}\n"
            f"- **Created At:** {timestamp}\n\n"
            f"---\n"
            f"### Description\n"
            f"{req.description.strip()}\n"
        )

    def _parse_issue(self, issue: Dict[str, Any], comments: Optional[List[TicketComment]] = None) -> TicketResponse:
        """Parse GitHub issue JSON dictionary into strongly-typed TicketResponse."""
        body = issue.get("body", "") or ""
        number = issue["number"]
        ticket_ref = f"GH-{number}"

        # Extract metadata from JSON comment if present
        meta_match = re.search(r"<!--\s*smartdesk_meta:\s*(\{.*?\})\s*-->", body, re.DOTALL)
        email = "unknown@novatech.com"
        category = "IT Support"
        priority = "Medium"

        if meta_match:
            try:
                meta_dict = json.loads(meta_match.group(1))
                email = meta_dict.get("employee_email", email)
                category = meta_dict.get("category", category)
                priority = meta_dict.get("priority", priority)
            except Exception:
                pass
        else:
            # Fallback regex extraction
            email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", body)
            if email_match:
                email = email_match.group(0).lower()

        # Map state: GitHub has 'open' or 'closed'
        state = issue.get("state", "open")
        labels = [lbl.get("name", "").lower() for lbl in issue.get("labels", []) if isinstance(lbl, dict)]
        if state == "closed":
            status = TicketStatus.CLOSED.value
        elif "in-progress" in labels or "in progress" in labels:
            status = TicketStatus.IN_PROGRESS.value
        elif "resolved" in labels:
            status = TicketStatus.RESOLVED.value
        else:
            status = TicketStatus.OPEN.value

        # Strip category prefix from title if present
        title = issue.get("title", "")
        title_clean = re.sub(r"^\[.*?\]\s*", "", title)

        # Clean description by removing metadata block
        description = re.sub(r"<!--\s*smartdesk_meta:.*?-->\s*", "", body, flags=re.DOTALL)
        description = re.sub(r"### SmartDesk AI Support Ticket.*?---\s*### Description\s*", "", description, flags=re.DOTALL).strip()
        if not description:
            description = body.strip()

        return TicketResponse(
            ticket_id=ticket_ref,
            employee_email=email,
            title=title_clean,
            description=description,
            category=category,
            priority=priority,
            status=status,
            created_at=issue.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=issue.get("updated_at", datetime.now(timezone.utc).isoformat()),
            comments=comments or [],
            url=issue.get("html_url", f"https://github.com/{self.owner}/{self.repo}/issues/{number}"),
            backend="github",
        )

    def _fetch_comments(self, issue_number: int) -> List[TicketComment]:
        """Fetch comments for an issue."""
        if not self.is_configured():
            return []
        try:
            url = f"{self.api_base}/issues/{issue_number}/comments"
            resp = requests.get(url, headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                comments_data = resp.json()
                return [
                    TicketComment(
                        author=c.get("user", {}).get("login", "Unknown"),
                        comment=c.get("body", ""),
                        created_at=c.get("created_at", datetime.now(timezone.utc).isoformat()),
                    )
                    for c in comments_data
                ]
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub comments for issue #{issue_number}: {e}")
        return []

    def create_ticket(self, req: TicketCreateRequest) -> TicketResponse:
        """Create a new issue on GitHub representing a support ticket."""
        if not self.is_configured():
            raise RuntimeError("GitHub backend is not properly configured.")

        now = datetime.now(timezone.utc).isoformat()
        body = self._build_body(req, now)
        title = f"[{req.category}] {req.title}"

        # Clean label strings
        cat_label = req.category.lower().replace(" ", "-").replace("&", "and")
        priority_label = f"priority:{req.priority.lower()}"
        labels = ["smartdesk-ticket", cat_label, priority_label]

        payload = {
            "title": title,
            "body": body,
            "labels": labels,
        }

        url = f"{self.api_base}/issues"
        resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=10)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"GitHub API error creating issue: {resp.status_code} - {resp.text}")

        issue_data = resp.json()
        return self._parse_issue(issue_data, comments=[])

    def get_ticket_by_id(self, ticket_id: str) -> Optional[TicketResponse]:
        """Fetch a ticket by ID (e.g. 'GH-42' or '42' or '#42')."""
        if not self.is_configured():
            return None

        # Extract numeric issue id
        num_match = re.search(r"\d+", ticket_id)
        if not num_match:
            return None
        issue_number = int(num_match.group(0))

        url = f"{self.api_base}/issues/{issue_number}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=6)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning(f"GitHub API error getting issue #{issue_number}: {resp.status_code}")
                return None

            issue_data = resp.json()
            comments = self._fetch_comments(issue_number)
            return self._parse_issue(issue_data, comments=comments)
        except Exception as e:
            logger.warning(f"Error fetching GitHub issue #{issue_number}: {e}")
            return None

    def get_tickets_by_email(self, email: str) -> List[TicketResponse]:
        """Fetch tickets created by or associated with a specific employee email."""
        if not self.is_configured():
            return []

        clean_email = email.lower().strip()
        url = f"{self.api_base}/issues?state=all&per_page=100"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=8)
            if resp.status_code != 200:
                return []

            issues = resp.json()
            results = []
            for issue in issues:
                if "pull_request" in issue:
                    continue  # skip pull requests
                parsed = self._parse_issue(issue)
                if parsed.employee_email.lower() == clean_email:
                    parsed.comments = self._fetch_comments(issue["number"])
                    results.append(parsed)
            return results
        except Exception as e:
            logger.warning(f"Error searching GitHub issues for {email}: {e}")
            return []

    def add_comment(self, ticket_id: str, author: str, comment: str) -> bool:
        """Add a comment to an existing GitHub issue ticket."""
        if not self.is_configured():
            return False

        num_match = re.search(r"\d+", ticket_id)
        if not num_match:
            return False
        issue_number = int(num_match.group(0))

        formatted_comment = f"**{author}:**\n\n{comment}"
        url = f"{self.api_base}/issues/{issue_number}/comments"
        try:
            resp = requests.post(url, headers=self._get_headers(), json={"body": formatted_comment}, timeout=6)
            return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"Error posting comment to GitHub issue #{issue_number}: {e}")
            return False

    def list_all_tickets(self, limit: int = 50) -> List[TicketResponse]:
        """List all recent tickets from GitHub Issues."""
        if not self.is_configured():
            return []

        url = f"{self.api_base}/issues?state=all&per_page={min(limit, 100)}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=8)
            if resp.status_code != 200:
                return []

            issues = resp.json()
            results = []
            for issue in issues:
                if "pull_request" in issue:
                    continue
                parsed = self._parse_issue(issue)
                results.append(parsed)
            return results
        except Exception as e:
            logger.warning(f"Error listing GitHub issues: {e}")
            return []
