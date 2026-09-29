"""
models/ticket.py — SQLAlchemy Ticket model.

This file defines two things:
  1. `db`     — the SQLAlchemy extension instance (shared across the app)
  2. `Ticket` — the database model that maps to the `tickets` table

Why define `db` here?
  - Flask-SQLAlchemy needs ONE db instance shared everywhere.
  - We create it here to avoid circular imports:
      app.py imports db from models.ticket
      models.ticket does NOT import from app.py
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

# The single SQLAlchemy instance.
# Initialised (bound to the Flask app) inside create_app() in app.py.
db = SQLAlchemy()


class Ticket(db.Model):
    """
    Represents a customer support ticket and its AI analysis.

    SQLAlchemy maps this class to a table called `tickets`.
    Each class attribute decorated with db.Column() becomes a column.
    """

    __tablename__ = "tickets"

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    id = db.Column(
        db.Integer,
        primary_key=True,
        comment="Auto-incrementing unique identifier",
    )
    message = db.Column(
        db.Text,
        nullable=False,
        comment="Original customer message",
    )
    category = db.Column(
        db.String(50),
        nullable=False,
        comment="AI-classified category: payment/shipping/account/product/technical/other",
    )
    priority = db.Column(
        db.String(20),
        nullable=False,
        comment="AI-assigned priority: low/medium/high/urgent",
    )
    sentiment = db.Column(
        db.String(20),
        nullable=False,
        comment="AI-detected sentiment: positive/neutral/negative",
    )
    summary = db.Column(
        db.Text,
        nullable=False,
        comment="Short AI-generated summary of the issue",
    )
    suggested_action = db.Column(
        db.Text,
        nullable=False,
        comment="AI-recommended next action for the support team",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="UTC timestamp when the ticket was created",
    )

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """
        Serialize this Ticket to a plain Python dictionary.

        Flask cannot return SQLAlchemy objects directly — they must be
        converted to JSON-serializable types first. This method is the
        single source of truth for what a ticket looks like in API responses.
        """
        return {
            "id": self.id,
            "message": self.message,
            "category": self.category,
            "priority": self.priority,
            "sentiment": self.sentiment,
            "summary": self.summary,
            "suggested_action": self.suggested_action,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        """Developer-friendly string representation for debugging."""
        return f"<Ticket id={self.id} category={self.category} priority={self.priority}>"
