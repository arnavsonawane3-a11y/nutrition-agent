"""
db.py — Neon (PostgreSQL) connection and schema helpers
========================================================
Tables created automatically on first use:

  user_profiles  — one row per session_id, stores profile JSON
  chat_history   — one row per message, linked to session_id
"""

import os
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # Neon connection string


def get_conn():
    """Open a new connection to Neon. Caller is responsible for closing it."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    """Create tables if they don't exist. Call once at app startup."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    session_id  TEXT PRIMARY KEY,
                    profile     JSONB        NOT NULL DEFAULT '{}',
                    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id          BIGSERIAL    PRIMARY KEY,
                    session_id  TEXT         NOT NULL,
                    role        TEXT         NOT NULL,   -- 'user' | 'assistant'
                    content     TEXT         NOT NULL,
                    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_session
                    ON chat_history (session_id, created_at)
            """)
        conn.commit()


# ── Profile helpers ────────────────────────────────────────────────────────────

def save_profile(session_id: str, profile: dict) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profiles (session_id, profile, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET profile = EXCLUDED.profile, updated_at = NOW()
            """, (session_id, json.dumps(profile)))
        conn.commit()


def load_profile(session_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT profile FROM user_profiles WHERE session_id = %s",
                (session_id,)
            )
            row = cur.fetchone()
    return dict(row["profile"]) if row else None


# ── Chat history helpers ───────────────────────────────────────────────────────

def append_message(session_id: str, role: str, content: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content)
            )
        conn.commit()


def get_recent_history(session_id: str, limit: int = 20) -> list[dict]:
    """Return the last `limit` messages for a session, oldest first."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT role, content FROM (
                    SELECT role, content, created_at
                    FROM chat_history
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at ASC
            """, (session_id, limit))
            rows = cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def clear_history(session_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chat_history WHERE session_id = %s",
                (session_id,)
            )
        conn.commit()
