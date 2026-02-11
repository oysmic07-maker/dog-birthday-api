import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DB_PATH = os.getenv("DB_PATH", "./data.sqlite3")
ADMIN_PASS = os.getenv("ADMIN_PASS", "0718")

# 예시:
# ALLOWED_ORIGINS="https://<YOUR_GH_USERNAME>.github.io,https://<YOUR_CUSTOM_DOMAIN>,http://localhost:8000"
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000",
)

origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]

app = FastAPI(title="Dog Birthday Guestbook API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _init_db() -> None:
    c = _conn()
    try:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS guestbook (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              name TEXT NOT NULL,
              message TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS rsvp (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              name TEXT NOT NULL,
              contact TEXT NOT NULL,
              attend TEXT NOT NULL,
              people INTEGER NOT NULL,
              memo TEXT
            )
            """
        )
        c.commit()
    finally:
        c.close()


_init_db()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _admin_guard(request: Request) -> None:
    p = request.headers.get("x-admin-pass") or request.query_params.get("pass")
    if not p or p != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _clean(s: str) -> str:
    return " ".join((s or "").strip().split())


class GuestbookIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=1, max_length=800)


class RSVPIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    contact: str = Field(min_length=3, max_length=80)
    attend: str = Field(min_length=2, max_length=10)  # yes/maybe/no
    people: int = Field(ge=1, le=20)
    memo: Optional[str] = Field(default="", max_length=300)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.post("/api/guestbook")
def create_guestbook(payload: GuestbookIn) -> Dict[str, Any]:
    name = _clean(payload.name)
    msg = _clean(payload.message)
    c = _conn()
    try:
        c.execute(
            "INSERT INTO guestbook (created_at, name, message) VALUES (?, ?, ?)",
            (_now_iso(), name, msg),
        )
        c.commit()
        new_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    finally:
        c.close()
    return {"ok": True, "id": new_id}


@app.get("/api/guestbook")
def list_guestbook(limit: int = 100) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, created_at, name, message FROM guestbook ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        c.close()
    return {"ok": True, "items": [dict(r) for r in rows]}


@app.delete("/api/guestbook/{item_id}")
def delete_guestbook(item_id: int, request: Request) -> Dict[str, Any]:
    _admin_guard(request)
    c = _conn()
    try:
        cur = c.execute("DELETE FROM guestbook WHERE id = ?", (int(item_id),))
        c.commit()
        if cur.rowcount <= 0:
            raise HTTPException(status_code=404, detail="Not found")
    finally:
        c.close()
    return {"ok": True}


@app.post("/api/rsvp")
def create_rsvp(payload: RSVPIn) -> Dict[str, Any]:
    name = _clean(payload.name)
    contact = _clean(payload.contact)
    attend = _clean(payload.attend)
    memo = _clean(payload.memo or "")
    people = int(payload.people)

    if attend not in ("yes", "maybe", "no"):
        raise HTTPException(status_code=400, detail="attend must be yes/maybe/no")

    c = _conn()
    try:
        c.execute(
            "INSERT INTO rsvp (created_at, name, contact, attend, people, memo) VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), name, contact, attend, people, memo),
        )
        c.commit()
        new_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    finally:
        c.close()

    return {"ok": True, "id": new_id}


@app.get("/api/rsvp")
def list_rsvp(request: Request, limit: int = 300) -> Dict[str, Any]:
    _admin_guard(request)
    limit = max(1, min(int(limit or 300), 1000))
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, created_at, name, contact, attend, people, memo FROM rsvp ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        c.close()
    return {"ok": True, "items": [dict(r) for r in rows]}
