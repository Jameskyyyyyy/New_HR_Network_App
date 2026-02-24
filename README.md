# Finance Recruiting Killer

Automate your finance networking outreach. Find the right people at Goldman, BlackRock, and Citadel — generate personalized cold emails and send them on autopilot.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in your API keys
cp .env.example .env
# Edit .env — add your GOOGLE_CLIENT_SECRET and HUNTER_API_KEY

# 3. Run the server
uvicorn backend.app.main:app --reload --port 8000

# 4. Open browser
open http://127.0.0.1:8000
```

## API Keys Required

| Key | Where to get it |
|-----|----------------|
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console → your OAuth client |
| `HUNTER_API_KEY` | hunter.io → API keys |
| `SERPAPI_KEY` | Already filled in `.env` |

## Architecture

```
backend/app/
├── main.py          FastAPI entry point + session middleware
├── config.py        Settings from .env
├── database.py      SQLAlchemy + SQLite setup
├── models/          ORM models (User, Campaign, Contact, Draft, Template, SendJob)
├── routers/         API endpoints (auth, campaigns, contacts, drafts, templates, send)
└── services/        Business logic (contact generation, drafting, sending, scheduling)

frontend/static/
├── index.html       Landing page (public)
├── login.html       Login / Google OAuth
├── app.html         Main app shell (all pages)
├── landing.css      Landing page styles
├── styles.css       App design system
└── app.js           App logic (~1500 lines)

scripts/
└── run_worker_loop.py   Standalone send worker (optional, embedded in main.py)
```

## Core Flow

1. Sign in with Google OAuth
2. Create a campaign — enter target firms, roles, location, schools
3. Click "Generate Contacts" — SerpAPI searches LinkedIn, Hunter.io finds emails
4. Review contacts by fit score, select who to email
5. Upload resume + pick a template → generate personalized drafts
6. Review & approve drafts in the split-panel editor
7. Set send schedule → click "Send Now" → emails go out from your Gmail

## Run Commands

```bash
# API server (includes embedded send worker)
uvicorn backend.app.main:app --reload --port 8000

# Optional: standalone send worker
python scripts/run_worker_loop.py
```
