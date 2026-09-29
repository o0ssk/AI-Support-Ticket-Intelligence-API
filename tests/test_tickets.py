"""
tests/test_tickets.py — Tests for all ticket CRUD endpoints.

Design principles:
  - Each test is independent (fresh DB per test via in-memory SQLite)
  - AI calls are MOCKED — tests never hit the real API
  - Tests are fast, deterministic, and repeatable
  - We test both success cases AND failure/edge cases

Run with:  pytest tests/ -v
"""

import pytest
from unittest.mock import patch, MagicMock

from app import create_app
from config import TestingConfig
from models.ticket import db as _db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """
    Create a fresh Flask app with in-memory SQLite for each test.

    Using a fixture means pytest handles setup/teardown automatically.
    The `yield` keyword splits setup (before yield) from teardown (after yield).
    """
    flask_app = create_app(TestingConfig)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client — lets us make HTTP requests without a real server."""
    return app.test_client()


@pytest.fixture
def mock_ai():
    """
    Patch the AI service so tests never call the real API.

    `patch` replaces `analyze_ticket` with a MagicMock for the duration
    of each test, then restores the real function afterward.

    Usage in test:
        def test_something(client, mock_ai):
            mock_ai.return_value = {...}
    """
    with patch("routes.tickets.analyze_ticket") as mock:
        mock.return_value = {
            "category": "payment",
            "priority": "high",
            "sentiment": "negative",
            "summary": "Customer reports a failed payment and duplicate charge.",
            "suggested_action": "Verify the transaction and investigate the duplicate charge.",
        }
        yield mock


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def create_test_ticket(client, mock_ai, message="My payment failed twice."):
    """Helper to create one ticket and return the response."""
    return client.post(
        "/api/tickets",
        json={"message": message},
        content_type="application/json",
    )


# ===========================================================================
# POST /api/tickets — Create ticket
# ===========================================================================

class TestCreateTicket:

    def test_create_ticket_success(self, client, mock_ai):
        """Happy path: valid message → AI runs → ticket saved → 201 returned."""
        response = create_test_ticket(client, mock_ai)

        assert response.status_code == 201
        data = response.get_json()

        # All required fields must be present
        assert data["id"] == 1
        assert data["message"] == "My payment failed twice."
        assert data["category"] == "payment"
        assert data["priority"] == "high"
        assert data["sentiment"] == "negative"
        assert "summary" in data
        assert "suggested_action" in data
        assert "created_at" in data

        # AI was called exactly once with the correct message
        mock_ai.assert_called_once_with("My payment failed twice.")

    def test_create_ticket_missing_message_field(self, client, mock_ai):
        """Missing 'message' key → 400."""
        response = client.post(
            "/api/tickets",
            json={"text": "wrong key"},
        )
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_create_ticket_empty_message(self, client, mock_ai):
        """Empty string → 400."""
        response = client.post("/api/tickets", json={"message": ""})
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_create_ticket_whitespace_only(self, client, mock_ai):
        """Whitespace-only message → 400."""
        response = client.post("/api/tickets", json={"message": "   "})
        assert response.status_code == 400

    def test_create_ticket_message_too_short(self, client, mock_ai):
        """Message shorter than MIN_MESSAGE_LENGTH → 400."""
        response = client.post("/api/tickets", json={"message": "Hi"})
        assert response.status_code == 400

    def test_create_ticket_message_too_long(self, client, mock_ai):
        """Message longer than MAX_MESSAGE_LENGTH → 400."""
        long_message = "x" * 2001
        response = client.post("/api/tickets", json={"message": long_message})
        assert response.status_code == 400

    def test_create_ticket_wrong_type(self, client, mock_ai):
        """Non-string message → 400."""
        response = client.post("/api/tickets", json={"message": 12345})
        assert response.status_code == 400

    def test_create_ticket_no_body(self, client, mock_ai):
        """No JSON body at all → 400."""
        response = client.post("/api/tickets", data="not json")
        assert response.status_code == 400

    def test_create_ticket_ai_unavailable(self, client, mock_ai):
        """AI connection error → 503."""
        mock_ai.side_effect = ConnectionError("AI is down")
        response = create_test_ticket(client, mock_ai)
        assert response.status_code == 503
        assert "error" in response.get_json()

    def test_create_ticket_ai_timeout(self, client, mock_ai):
        """AI timeout → 504."""
        mock_ai.side_effect = TimeoutError("timed out")
        response = create_test_ticket(client, mock_ai)
        assert response.status_code == 504

    def test_create_ticket_ai_invalid_response(self, client, mock_ai):
        """AI returns bad data → 502."""
        mock_ai.side_effect = ValueError("Invalid JSON from AI")
        response = create_test_ticket(client, mock_ai)
        assert response.status_code == 502


# ===========================================================================
# GET /api/tickets — List all tickets
# ===========================================================================

class TestGetTickets:

    def test_get_tickets_empty(self, client):
        """No tickets in DB → empty list."""
        response = client.get("/api/tickets")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_get_tickets_returns_all(self, client, mock_ai):
        """Multiple tickets → all returned."""
        create_test_ticket(client, mock_ai, "Payment issue one.")
        create_test_ticket(client, mock_ai, "Payment issue two.")
        create_test_ticket(client, mock_ai, "Payment issue three.")

        response = client.get("/api/tickets")
        assert response.status_code == 200
        assert len(response.get_json()) == 3

    def test_get_tickets_newest_first(self, client, mock_ai):
        """Tickets should be returned newest first."""
        create_test_ticket(client, mock_ai, "First ticket created here.")
        create_test_ticket(client, mock_ai, "Second ticket created now.")

        response = client.get("/api/tickets")
        tickets = response.get_json()
        # Newest (id=2) should be first
        assert tickets[0]["id"] == 2
        assert tickets[1]["id"] == 1

    def test_get_tickets_filter_by_category(self, client, mock_ai):
        """Filter by category query param."""
        create_test_ticket(client, mock_ai)  # category = payment

        mock_ai.return_value = {
            "category": "shipping",
            "priority": "medium",
            "sentiment": "neutral",
            "summary": "Order delayed.",
            "suggested_action": "Check shipping status.",
        }
        create_test_ticket(client, mock_ai, "Where is my order from last week?")

        response = client.get("/api/tickets?category=payment")
        tickets = response.get_json()
        assert len(tickets) == 1
        assert tickets[0]["category"] == "payment"


# ===========================================================================
# GET /api/tickets/<id> — Get single ticket
# ===========================================================================

class TestGetTicketById:

    def test_get_existing_ticket(self, client, mock_ai):
        """Valid ID → 200 with ticket data."""
        create_test_ticket(client, mock_ai)

        response = client.get("/api/tickets/1")
        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == 1
        assert data["category"] == "payment"

    def test_get_nonexistent_ticket(self, client):
        """Non-existent ID → 404."""
        response = client.get("/api/tickets/999")
        assert response.status_code == 404
        assert "error" in response.get_json()

    def test_get_ticket_error_message_is_safe(self, client):
        """404 error should not expose internal details."""
        response = client.get("/api/tickets/999")
        error_msg = response.get_json()["error"]
        # Should not contain stack traces or file paths
        assert "Traceback" not in error_msg
        assert "File" not in error_msg


# ===========================================================================
# DELETE /api/tickets/<id> — Delete ticket
# ===========================================================================

class TestDeleteTicket:

    def test_delete_existing_ticket(self, client, mock_ai):
        """Valid ID → ticket deleted → 200."""
        create_test_ticket(client, mock_ai)

        response = client.delete("/api/tickets/1")
        assert response.status_code == 200
        assert "message" in response.get_json()

        # Verify it's gone
        get_response = client.get("/api/tickets/1")
        assert get_response.status_code == 404

    def test_delete_nonexistent_ticket(self, client):
        """Non-existent ID → 404."""
        response = client.delete("/api/tickets/999")
        assert response.status_code == 404

    def test_delete_reduces_ticket_count(self, client, mock_ai):
        """After deleting, the list count should decrease."""
        create_test_ticket(client, mock_ai, "First ticket message here.")
        create_test_ticket(client, mock_ai, "Second ticket message here.")

        client.delete("/api/tickets/1")

        response = client.get("/api/tickets")
        assert len(response.get_json()) == 1
