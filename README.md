# AI Support Ticket Intelligence API

A production-ready Flask REST API that uses AI to automatically analyze customer support tickets — classifying category, detecting sentiment, assigning priority, generating summaries, and recommending actions.

Built as a portfolio project demonstrating real backend engineering skills: REST APIs, SQLAlchemy, AI/LLM integration, input validation, structured error handling, logging, analytics with Pandas, and a full test suite.

---

## The Problem

Support teams manually read every ticket to determine:
- What type of issue is it?
- How urgent is it?
- What does the customer feel?
- What should we do next?

This doesn't scale. When ticket volume grows, triage becomes a bottleneck.

## The Solution

An API that takes a raw customer message and returns structured intelligence — instantly.

```
Client → Flask API → Validation → AI Service → Result Validation → Database → Response
```

**Input:**
```json
{ "message": "My payment failed twice and I was charged double." }
```

**Output:**
```json
{
  "id": 1,
  "message": "My payment failed twice and I was charged double.",
  "category": "payment",
  "priority": "high",
  "sentiment": "negative",
  "summary": "Customer's payment failed twice and was charged double.",
  "suggested_action": "Review the customer's payment history and refund the excess amount immediately.",
  "created_at": "2026-09-29T11:02:45.883604"
}
```

---

## Features

- **AI ticket analysis** — category, priority, sentiment, summary, suggested action
- **Input validation** — rejects empty, too short, too long, or malformed messages
- **AI output validation** — validates all AI fields before saving to database
- **Full CRUD** — create, read, delete tickets
- **Filtering** — filter tickets by category, priority, or sentiment
- **Analytics** — Pandas-powered aggregate statistics
- **Structured logging** — rotating file + console with timestamps
- **Rate limiting** — prevents API abuse (10 req/min by default)
- **Error handling** — intentional, consistent JSON errors for every failure mode
- **29 automated tests** — fast, mocked AI, full coverage of happy and error paths
- **PostgreSQL-ready** — one environment variable change to switch databases

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | Flask 3.x |
| Database ORM | SQLAlchemy + Flask-SQLAlchemy |
| Database | SQLite (dev) / PostgreSQL (prod) |
| AI Provider | OpenRouter (OpenAI-compatible API) |
| AI SDK | openai Python SDK (v1.x) |
| Analytics | Pandas |
| Testing | pytest + pytest-mock |
| Rate Limiting | Flask-Limiter |
| Environment | python-dotenv |
| Production Server | gunicorn |

---

## Architecture

```
Client HTTP Request
        ↓
    Flask Route
  (routes/tickets.py)
        ↓
  Input Validation
  (message format, length, type)
        ↓
    AI Service
  (services/ai_service.py)
        ↓
  OpenRouter API
  (LLaMA / any OpenAI-compatible model)
        ↓
  Structured JSON
        ↓
  AI Result Validation
  (category / priority / sentiment whitelist)
        ↓
  SQLAlchemy ORM
  (models/ticket.py)
        ↓
  SQLite / PostgreSQL
        ↓
  JSON Response (201 Created)
```

---

## Project Structure

```
supportflow/
├── app.py                  # Flask app factory, error handlers, /health
├── config.py               # Config classes for dev / prod / test
├── requirements.txt        # Pinned dependencies
├── .env                    # Secrets (never committed)
├── .env.example            # Template (safe to commit)
├── .gitignore
├── README.md
│
├── routes/
│   └── tickets.py          # All HTTP endpoints
│
├── services/
│   └── ai_service.py       # AI integration + prompt + validation
│
├── models/
│   └── ticket.py           # SQLAlchemy Ticket model + db instance
│
├── utils/
│   └── logger.py           # Rotating file logger setup
│
├── tests/
│   ├── test_tickets.py     # CRUD endpoint tests (mocked AI)
│   └── test_analytics.py   # Analytics endpoint tests
│
└── instance/               # SQLite DB lives here (git-ignored)
```

---

## Installation

### Prerequisites
- Python 3.11+ (tested on 3.14)
- An [OpenRouter](https://openrouter.ai/keys) API key (free account available)

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-support-ticket-api.git
cd ai-support-ticket-api/supportflow

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Environment Setup

```bash
# Copy the example file
copy .env.example .env   # Windows
cp .env.example .env     # macOS/Linux
```

Edit `.env` and fill in your values:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct
FLASK_ENV=development
FLASK_DEBUG=true
SECRET_KEY=your-random-secret-key
DATABASE_URL=sqlite:///supportflow.db
RATE_LIMIT=10 per minute
```

Get your free API key at **https://openrouter.ai/keys**

---

## Running the Project

```bash
python app.py
```

Server starts at `http://127.0.0.1:5000`

---

## API Reference

### Health Check
```http
GET /health
```
```json
{ "status": "ok", "service": "AI Support Ticket Intelligence API", "database": "connected" }
```

---

### Create Ticket
```http
POST /api/tickets
Content-Type: application/json

{ "message": "My payment failed twice and I was charged double." }
```

**201 Created:**
```json
{
  "id": 1,
  "message": "My payment failed twice and I was charged double.",
  "category": "payment",
  "priority": "high",
  "sentiment": "negative",
  "summary": "Customer's payment failed twice and was charged double.",
  "suggested_action": "Review payment history and refund the excess amount immediately.",
  "created_at": "2026-09-29T11:02:45.883604"
}
```

**curl example:**
```bash
curl -X POST http://127.0.0.1:5000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{"message": "My payment failed twice and I was charged double."}'
```

---

### Get All Tickets
```http
GET /api/tickets
GET /api/tickets?category=payment
GET /api/tickets?priority=high
GET /api/tickets?sentiment=negative
```

```bash
curl http://127.0.0.1:5000/api/tickets
curl "http://127.0.0.1:5000/api/tickets?category=payment&priority=high"
```

---

### Get Ticket by ID
```http
GET /api/tickets/<id>
```

```bash
curl http://127.0.0.1:5000/api/tickets/1
```

Returns `404` with `{"error": "Ticket with id 1 not found."}` if not found.

---

### Delete Ticket
```http
DELETE /api/tickets/<id>
```

```bash
curl -X DELETE http://127.0.0.1:5000/api/tickets/1
```

---

### Analytics
```http
GET /api/analytics
```

```json
{
  "total_tickets": 50,
  "urgent_tickets": 3,
  "high_priority": 12,
  "negative_sentiment": 20,
  "most_common_category": "payment",
  "categories": { "payment": 18, "shipping": 14, "account": 10, "product": 8 },
  "priorities": { "high": 12, "medium": 21, "low": 14, "urgent": 3 },
  "sentiments": { "negative": 20, "neutral": 18, "positive": 12 }
}
```

```bash
curl http://127.0.0.1:5000/api/analytics
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --tb=short
```

All 29 tests run in ~1.5 seconds. AI calls are mocked — no API quota used during testing.

---

## Validation Rules

| Rule | Response |
|---|---|
| Missing `message` field | 400 — `"Field 'message' is required."` |
| Empty string | 400 — `"Field 'message' cannot be empty."` |
| Message < 5 chars | 400 — `"Message is too short (minimum 5 characters)."` |
| Message > 2000 chars | 400 — `"Message is too long (maximum 2000 characters)."` |
| Non-string message | 400 — `"Field 'message' must be a string."` |
| No JSON body | 400 — `"Request body must be JSON."` |
| AI unavailable | 503 |
| AI timeout | 504 |
| AI returns invalid JSON | 502 |

---

## HTTP Status Codes Used

| Code | Meaning |
|---|---|
| 200 | OK — GET / DELETE success |
| 201 | Created — POST ticket success |
| 400 | Bad Request — invalid input |
| 404 | Not Found — ticket doesn't exist |
| 429 | Too Many Requests — rate limit exceeded |
| 500 | Internal Server Error |
| 502 | Bad Gateway — AI returned invalid response |
| 503 | Service Unavailable — AI is down |
| 504 | Gateway Timeout — AI timed out |

---

## Switching to PostgreSQL

Change one line in `.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/supportflow
```

Install the driver:
```bash
pip install psycopg2-binary
```

No code changes required. SQLAlchemy handles the rest.

---

## Security Practices

- API keys stored only in `.env`, never in code
- `.env` listed in `.gitignore` and never committed
- Input validation on all endpoints (type, length, format)
- Stack traces never exposed to clients
- Rate limiting on all endpoints (configurable)
- AI output validated before database write

---

## Logs

Application logs are written to `logs/supportflow.log` and the console.

Format:
```
[2026-09-29 11:02:44] INFO     supportflow — POST /api/tickets — new ticket received
[2026-09-29 11:02:45] INFO     supportflow — Sending ticket to AI model: meta-llama/llama-3.1-8b-instruct
[2026-09-29 11:02:45] INFO     supportflow — AI analysis complete — category=payment priority=high sentiment=negative
[2026-09-29 11:02:45] INFO     supportflow — Ticket #1 saved to database.
```

Logs rotate at 5 MB and keep 3 backup files.


