# Blog Engine

## Project Overview
We are building a blog engine on a **$10 budget**. Keep everything lean, simple, and cost-effective.

## Tech Stack
- **Backend**: FastAPI (Python)
- **Database**: SQLite (via SQLAlchemy ORM)
- **Server**: Uvicorn

## Constraints
- $10 total budget — no paid APIs, no paid hosting tiers, no premium services
- SQLite only — no external database servers
- Minimize dependencies — only add packages when truly necessary
- Target deployment on free/cheap platforms (e.g., fly.io free tier, Railway starter, or a small VPS)

## Project Structure
```
app/
  main.py        — FastAPI application entry point
  models.py      — SQLAlchemy models
  schemas.py     — Pydantic request/response schemas
  database.py    — Database connection and session management
```

## Development
- Activate venv: `source venv/Scripts/activate` (Windows) or `source venv/bin/activate` (Linux/Mac)
- Install deps: `pip install -r requirements.txt`
- Run server: `uvicorn app.main:app --reload`
- Database file: `blog.db` (auto-created on first run)

## Conventions
- Use type hints everywhere
- Keep endpoints in `main.py` until complexity warrants splitting into routers
- Use Pydantic schemas for all request/response validation
- Write raw SQL only if SQLAlchemy ORM is insufficient
