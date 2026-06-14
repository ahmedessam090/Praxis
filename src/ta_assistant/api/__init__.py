"""FastAPI service — the HTTP bridge between the Next.js frontend and the Python core
(Temporal workflows + SQLite). Serves the existing pydantic models as JSON and
triggers/polls the durable workflows. All heavy work stays in the workflows/activities."""
