"""
tests/test_analytics.py — Tests for the analytics endpoint.

The analytics endpoint uses Pandas for aggregation.
These tests verify the output structure and correctness.
"""

import pytest
from unittest.mock import patch

from app import create_app
from config import TestingConfig
from models.ticket import db as _db


@pytest.fixture
def app():
    flask_app = create_app(TestingConfig)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_ticket(client, message, ai_result):
    """Helper to create a ticket with a specific AI result."""
    with patch("routes.tickets.analyze_ticket", return_value=ai_result):
        return client.post("/api/tickets", json={"message": message})


class TestAnalytics:

    def test_analytics_no_tickets(self, client):
        """Empty database → zeroed response."""
        response = client.get("/api/analytics")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_tickets"] == 0
        assert data["categories"] == {}
        assert data["priorities"] == {}
        assert data["sentiments"] == {}

    def test_analytics_total_count(self, client):
        """Total ticket count is correct."""
        ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "Payment failed.",
            "suggested_action": "Verify transaction.",
        }
        _make_ticket(client, "My payment failed twice yesterday.", ai)
        _make_ticket(client, "Payment charged double the amount.", ai)
        _make_ticket(client, "Cannot process my payment at all.", ai)

        response = client.get("/api/analytics")
        assert response.get_json()["total_tickets"] == 3

    def test_analytics_category_breakdown(self, client):
        """Categories dict contains correct counts."""
        payment_ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "Payment issue.",
            "suggested_action": "Check payment.",
        }
        shipping_ai = {
            "category": "shipping", "priority": "medium",
            "sentiment": "neutral", "summary": "Shipping delay.",
            "suggested_action": "Check order status.",
        }

        _make_ticket(client, "My payment failed twice.", payment_ai)
        _make_ticket(client, "Payment charged double.", payment_ai)
        _make_ticket(client, "Where is my order from last week?", shipping_ai)

        data = client.get("/api/analytics").get_json()
        assert data["categories"]["payment"] == 2
        assert data["categories"]["shipping"] == 1

    def test_analytics_priority_breakdown(self, client):
        """Priority counts are correct."""
        high_ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "High priority issue.",
            "suggested_action": "Resolve immediately.",
        }
        low_ai = {
            "category": "account", "priority": "low",
            "sentiment": "neutral", "summary": "Low priority question.",
            "suggested_action": "Send information.",
        }

        _make_ticket(client, "My payment failed twice here.", high_ai)
        _make_ticket(client, "How do I change my username please?", low_ai)

        data = client.get("/api/analytics").get_json()
        assert data["priorities"]["high"] == 1
        assert data["priorities"]["low"] == 1

    def test_analytics_high_priority_count(self, client):
        """high_priority field counts only 'high' priority tickets."""
        high_ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "Payment issue.",
            "suggested_action": "Check payment.",
        }
        urgent_ai = {
            "category": "technical", "priority": "urgent",
            "sentiment": "negative", "summary": "System down.",
            "suggested_action": "Escalate immediately.",
        }

        _make_ticket(client, "My payment failed twice yesterday.", high_ai)
        _make_ticket(client, "System is completely down right now.", urgent_ai)

        data = client.get("/api/analytics").get_json()
        assert data["high_priority"] == 1
        assert data["urgent_tickets"] == 1

    def test_analytics_negative_sentiment_count(self, client):
        """negative_sentiment field is correct."""
        negative_ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "Angry customer.",
            "suggested_action": "Apologize and fix.",
        }
        positive_ai = {
            "category": "product", "priority": "low",
            "sentiment": "positive", "summary": "Happy customer.",
            "suggested_action": "Thank the customer.",
        }

        _make_ticket(client, "I am very angry about the charge.", negative_ai)
        _make_ticket(client, "I love your product so very much!", positive_ai)

        data = client.get("/api/analytics").get_json()
        assert data["negative_sentiment"] == 1

    def test_analytics_most_common_category(self, client):
        """most_common_category is the category with most tickets."""
        shipping_ai = {
            "category": "shipping", "priority": "medium",
            "sentiment": "neutral", "summary": "Shipping issue.",
            "suggested_action": "Check delivery.",
        }
        payment_ai = {
            "category": "payment", "priority": "high",
            "sentiment": "negative", "summary": "Payment issue.",
            "suggested_action": "Check payment.",
        }

        _make_ticket(client, "Where is my order from yesterday?", shipping_ai)
        _make_ticket(client, "My order has not arrived yet.", shipping_ai)
        _make_ticket(client, "I was charged twice for the order.", payment_ai)

        data = client.get("/api/analytics").get_json()
        assert data["most_common_category"] == "shipping"

    def test_analytics_response_has_all_required_keys(self, client):
        """Response always contains all expected keys."""
        ai = {
            "category": "account", "priority": "low",
            "sentiment": "neutral", "summary": "Account issue.",
            "suggested_action": "Reset account.",
        }
        _make_ticket(client, "I cannot log in to my account now.", ai)

        data = client.get("/api/analytics").get_json()
        required_keys = [
            "total_tickets", "urgent_tickets", "high_priority",
            "negative_sentiment", "most_common_category",
            "categories", "priorities", "sentiments",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
