"""
Ticketing Data Models for SmartDesk AI.
Defines strongly-typed Pydantic schemas for ticket creation, status checks, and comments.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


class TicketStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class TicketPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class TicketCategory(str, Enum):
    IT_SUPPORT = "IT Support"
    HR_POLICIES = "HR Policies"
    FACILITIES = "Workplace & Facilities"
    SECURITY = "Physical Security"
    GENERAL = "General Operations"


class TicketComment(BaseModel):
    author: str
    comment: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TicketCreateRequest(BaseModel):
    employee_email: str = Field(..., description="Corporate email address of the employee")
    title: str = Field(..., description="Short, descriptive one-line summary of the issue")
    description: str = Field(..., description="Detailed explanation of the issue and context")
    category: str = Field(default=TicketCategory.IT_SUPPORT.value, description="Domain/Department category")
    priority: str = Field(default=TicketPriority.MEDIUM.value, description="Issue urgency level")


class TicketResponse(BaseModel):
    ticket_id: str
    employee_email: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    created_at: str
    updated_at: str
    comments: List[TicketComment] = Field(default_factory=list)
    url: str
    backend: str = "sqlite"
