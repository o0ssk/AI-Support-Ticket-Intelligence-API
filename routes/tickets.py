"""
routes/tickets.py — All ticket-related HTTP endpoints.

This file only handles HTTP concerns:
  - Parse the incoming request
  - Validate input
  - Call the appropriate service or model
  - Return a structured JSON response with the correct HTTP status code

It does NOT contain AI logic or raw SQL.
That separation makes each layer independently testable.

Endpoints:
  POST   /api/tickets          → Create and analyze a ticket
  GET    /api/tickets          → List all tickets
  GET    /api/tickets/<id>     → Get a specific ticket
  DELETE /api/tickets/<id>     → Delete a specific ticket
  GET    /api/analytics        → Ticket statistics
"""

import pandas as pd
from flask import Blueprint, request, jsonify, current_app

from models.ticket import db, Ticket
from services.ai_service import analyze_ticket
from utils.logger import logger

# A Blueprint is Flask's way of grouping related routes.
# We register this blueprint in app.py with a URL prefix of /api.
tickets_bp = Blueprint("tickets", __name__)


# ===========================================================================
# Input validation helper
# ===========================================================================

def _validate_message(data: dict | None) -> tuple[str | None, str | None]:
    """
    Validate the incoming request body for ticket creation.

    Returns:
        (message, error_string) — exactly one of them will be None.
        If error_string is not None, return a 400 immediately.
    """
    if data is None:
        return None, "Request body must be JSON."

    message = data.get("message")

    if message is None:
        return None, "Field 'message' is required."

    if not isinstance(message, str):
        return None, "Field 'message' must be a string."

    message = message.strip()

    if len(message) == 0:
        return None, "Field 'message' cannot be empty."

    config = current_app.config
    min_len = config.get("MIN_MESSAGE_LENGTH", 5)
    max_len = config.get("MAX_MESSAGE_LENGTH", 2000)

    if len(message) < min_len:
        return None, f"Message is too short (minimum {min_len} characters)."

    if len(message) > max_len:
        return None, f"Message is too long (maximum {max_len} characters)."

    return message, None


# ===========================================================================
# POST /api/tickets — Create and analyze a ticket
# ===========================================================================

@tickets_bp.route("/tickets", methods=["POST"])
def create_ticket():
    """
    Accept a customer message, run AI analysis, save to DB, return result.

    Flow:
      1. Parse JSON body
      2. Validate 'message' field
      3. Call AI service
      4. Save result to database
      5. Return 201 Created with full ticket data
    """
    logger.info("POST /api/tickets — new ticket received")

    # Step 1: Parse JSON body
    # silent=True returns None instead of raising an error on bad JSON
    data = request.get_json(silent=True)

    # Step 2: Validate input
    message, error = _validate_message(data)
    if error:
        logger.warning("Ticket validation failed: %s", error)
        return jsonify({"error": error}), 400

    # Step 3: Call AI service
    try:
        ai_result = analyze_ticket(message)
    except ConnectionError as e:
        logger.error("AI connection error: %s", str(e))
        return jsonify({"error": "AI service is currently unavailable. Please try again."}), 503
    except TimeoutError as e:
        logger.error("AI timeout: %s", str(e))
        return jsonify({"error": "AI service timed out. Please try again."}), 504
    except ValueError as e:
        logger.error("AI returned invalid response: %s", str(e))
        return jsonify({"error": "AI returned an unexpected response. Please try again."}), 502
    except RuntimeError as e:
        logger.error("AI runtime error: %s", str(e))
        return jsonify({"error": str(e)}), 502

    # Step 4: Save to database
    try:
        ticket = Ticket(
            message=message,
            category=ai_result["category"],
            priority=ai_result["priority"],
            sentiment=ai_result["sentiment"],
            summary=ai_result["summary"],
            suggested_action=ai_result["suggested_action"],
        )
        db.session.add(ticket)
        db.session.commit()
        logger.info("Ticket #%d saved to database.", ticket.id)
    except Exception as e:
        db.session.rollback()
        logger.error("Database error saving ticket: %s", str(e))
        return jsonify({"error": "Failed to save ticket. Please try again."}), 500

    # Step 5: Return the created ticket
    return jsonify(ticket.to_dict()), 201


# ===========================================================================
# GET /api/tickets — List all tickets
# ===========================================================================

@tickets_bp.route("/tickets", methods=["GET"])
def get_tickets():
    """
    Return all tickets, newest first.

    Optional query parameters:
      ?category=payment     Filter by category
      ?priority=high        Filter by priority
      ?sentiment=negative   Filter by sentiment
    """
    logger.info("GET /api/tickets — listing tickets")

    query = Ticket.query

    # Optional filters
    category = request.args.get("category", "").lower().strip()
    priority = request.args.get("priority", "").lower().strip()
    sentiment = request.args.get("sentiment", "").lower().strip()

    if category:
        query = query.filter(Ticket.category == category)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if sentiment:
        query = query.filter(Ticket.sentiment == sentiment)

    tickets = query.order_by(Ticket.created_at.desc()).all()

    logger.info("Returning %d ticket(s)", len(tickets))
    return jsonify([t.to_dict() for t in tickets]), 200


# ===========================================================================
# GET /api/tickets/<id> — Get a single ticket
# ===========================================================================

@tickets_bp.route("/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket(ticket_id: int):
    """Return a single ticket by ID, or 404 if not found."""
    logger.info("GET /api/tickets/%d", ticket_id)

    ticket = db.session.get(Ticket, ticket_id)

    if ticket is None:
        logger.warning("Ticket #%d not found", ticket_id)
        return jsonify({"error": f"Ticket with id {ticket_id} not found."}), 404

    return jsonify(ticket.to_dict()), 200


# ===========================================================================
# DELETE /api/tickets/<id> — Delete a ticket
# ===========================================================================

@tickets_bp.route("/tickets/<int:ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id: int):
    """Delete a ticket by ID. Returns 404 if not found, 200 on success."""
    logger.info("DELETE /api/tickets/%d", ticket_id)

    ticket = db.session.get(Ticket, ticket_id)

    if ticket is None:
        logger.warning("Attempted to delete non-existent ticket #%d", ticket_id)
        return jsonify({"error": f"Ticket with id {ticket_id} not found."}), 404

    try:
        db.session.delete(ticket)
        db.session.commit()
        logger.info("Ticket #%d deleted.", ticket_id)
    except Exception as e:
        db.session.rollback()
        logger.error("Database error deleting ticket #%d: %s", ticket_id, str(e))
        return jsonify({"error": "Failed to delete ticket. Please try again."}), 500

    return jsonify({"message": f"Ticket {ticket_id} deleted successfully."}), 200


# ===========================================================================
# GET /api/analytics — Aggregate ticket statistics
# ===========================================================================

@tickets_bp.route("/analytics", methods=["GET"])
def get_analytics():
    """
    Return aggregate statistics about all tickets.

    Uses Pandas for analysis because:
    - Percentage calculations and multi-level aggregations are more readable
    - Easy to extend with more complex analysis later
    - Demonstrates real-world Pandas usage on relational data

    For simple counts (total, high_priority) we use SQL directly —
    that's more efficient than loading all rows into memory.
    """
    logger.info("GET /api/analytics — analytics requested")

    total = db.session.query(Ticket).count()

    if total == 0:
        return jsonify({
            "total_tickets": 0,
            "urgent_tickets": 0,
            "high_priority": 0,
            "negative_sentiment": 0,
            "most_common_category": None,
            "categories": {},
            "priorities": {},
            "sentiments": {},
        }), 200

    # Load all tickets into a Pandas DataFrame for analysis
    tickets = db.session.query(
        Ticket.category,
        Ticket.priority,
        Ticket.sentiment,
    ).all()

    df = pd.DataFrame(tickets, columns=["category", "priority", "sentiment"])

    # --- Aggregations -------------------------------------------------------

    # Count by category → dict like {"payment": 18, "shipping": 14, ...}
    categories = df["category"].value_counts().to_dict()

    # Count by priority
    priorities = df["priority"].value_counts().to_dict()

    # Count by sentiment
    sentiments = df["sentiment"].value_counts().to_dict()

    # Most common category
    most_common_category = df["category"].value_counts().idxmax()

    # Specific counts used in the summary section
    urgent_count = int(df[df["priority"] == "urgent"].shape[0])
    high_priority_count = int(df[df["priority"] == "high"].shape[0])
    negative_count = int(df[df["sentiment"] == "negative"].shape[0])

    result = {
        "total_tickets": total,
        "urgent_tickets": urgent_count,
        "high_priority": high_priority_count,
        "negative_sentiment": negative_count,
        "most_common_category": most_common_category,
        "categories": categories,
        "priorities": priorities,
        "sentiments": sentiments,
    }

    logger.info("Analytics: total=%d categories=%s", total, list(categories.keys()))
    return jsonify(result), 200
