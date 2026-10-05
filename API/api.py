"""
Mock "Contact Centre Platform" REST API (serves SYNTHETIC data from data/raw/).

Run:
    uvicorn api:app --port 8000
Docs (auto-generated, try requests in the browser):
    http://localhost:8000/docs

You don't need to read or modify this file: treat it as a third-party system
you don't control, the way you would a real vendor API.

Behaviour worth knowing about (this is what a real API is like):
  * Auth: every /api/v1 request needs header  X-API-Key: demo-key
  * Pagination: limit (1-500, default 100) + offset. Response has meta.next_offset
  * Incremental: ?updated_since=2026-08-31T23:59:59  (INCLUSIVE, so boundary rows can
    come back again. Your load must be idempo`tent.)
  * "Time" moves: the API only shows records with updated_at <= its current as-of time.
    Start = 2026-08-31. Call POST /admin/advance?days=7 to make a week of new data arrive.
  * Optional flaky mode:  FLAKY=1 uvicorn api:app  -> random 429 / 503 errors,
    so you can practise retries with back-off.
"""
import bisect
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

BASE = Path(__file__).parent / "data" / "raw"
API_KEY = os.getenv("API_KEY", "demo-key")
FLAKY = os.getenv("FLAKY", "0") == "1"
DEFAULT_AS_OF = "2026-08-31T23:59:59"
MAX_AS_OF = "2026-09-28T23:59:59"

# resource -> (file, id field, time-gated?)
RESOURCES = {
    "teams": ("teams.json", "team_id", False),
    "agents": ("agents.json", "agent_id", False),
    "customers": ("customers.json", "customer_id", False),
    "interactions": ("interactions.json", "interaction_id", True),
    "surveys": ("surveys.json", "survey_id", True),
    "qa-evaluations": ("qa_evaluations.json", "qa_id", True),
    "shifts": ("shifts.json", "shift_id", True),
}

DATA, KEYS = {}, {}
STATE = {"as_of": DEFAULT_AS_OF}

app = FastAPI(title="Contact Centre Platform API (synthetic)", version="1.0")


def _load():
    for res, (fn, idf, gated) in RESOURCES.items():
        path = BASE / fn
        if not path.exists():
            raise RuntimeError(f"{path} not found. Run: python generate_data.py")
        rows = json.loads(path.read_text())
        if gated:
            rows.sort(key=lambda r: (r["updated_at"], str(r[idf])))
            KEYS[res] = [r["updated_at"] for r in rows]
        DATA[res] = rows


_load()


def _auth(key):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


def _valid_iso(s, name):
    try:
        datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be ISO format, e.g. 2026-08-31T23:59:59")


@app.get("/")
def root():
    return {"service": "Contact Centre Platform API (synthetic data)", "docs": "/docs",
            "resources": [f"/api/v1/{r}" for r in RESOURCES], "as_of": STATE["as_of"]}


@app.get("/health")
def health():
    return {"status": "ok", "as_of": STATE["as_of"], "flaky_mode": FLAKY}


@app.get("/api/v1/{resource}")
def list_resource(resource: str,
                  limit: int = Query(100, ge=1, le=500),
                  offset: int = Query(0, ge=0),
                  updated_since: Optional[str] = None,
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if resource not in RESOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown resource. Options: {list(RESOURCES)}")
    if FLAKY:
        r = random.random()
        if r < 0.03:
            return JSONResponse({"error": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "2"})
        if r < 0.06:
            return JSONResponse({"error": "service temporarily unavailable"}, status_code=503)

    rows = DATA[resource]
    if RESOURCES[resource][2]:
        keys = KEYS[resource]
        lo, hi = 0, bisect.bisect_right(keys, STATE["as_of"])
        if updated_since:
            _valid_iso(updated_since, "updated_since")
            lo = bisect.bisect_left(keys, updated_since)
        window = (lo, max(lo, hi))
    else:
        window = (0, len(rows))
    total = window[1] - window[0]
    start = window[0] + offset
    end = min(start + limit, window[1])
    page = rows[start:end] if start < window[1] else []
    nxt = offset + limit if (offset + limit) < total else None
    return {"data": page,
            "meta": {"resource": resource, "total": total, "limit": limit, "offset": offset,
                     "next_offset": nxt, "as_of": STATE["as_of"]}}


@app.get("/admin/as-of")
def get_as_of(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {"as_of": STATE["as_of"]}


@app.post("/admin/advance")
def advance(days: int = Query(7, ge=1, le=60), x_api_key: Optional[str] = Header(None)):
    """Simulate new data arriving: moves the API clock forward."""
    _auth(x_api_key)
    new = datetime.fromisoformat(STATE["as_of"]) + timedelta(days=days)
    STATE["as_of"] = min(new, datetime.fromisoformat(MAX_AS_OF)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"as_of": STATE["as_of"], "at_end_of_data": STATE["as_of"] == MAX_AS_OF}


@app.post("/admin/reset")
def reset(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    STATE["as_of"] = DEFAULT_AS_OF
    return {"as_of": STATE["as_of"]}
