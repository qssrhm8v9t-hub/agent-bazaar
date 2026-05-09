"""
Agent Bazaar - Reputation System
Calculates agent reputation from execution traces.
Reputation = base + completion_bonus - penalties.
Each reputation change is recorded as an immutable (encrypted) event.

Security: IQR outlier filtering for ratings, encrypted storage.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import load_json, save_json

try:
    from .tracer import get_traces_for_agent, get_traces_for_match
    from .matching import list_matches
except ImportError:
    from tracer import get_traces_for_agent, get_traces_for_match
    from matching import list_matches

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REP_FILE = "reputation.json"
REP_EVENTS_FILE = "reputation_events.jsonl"

# Reputation tiers
TIERS = [
    ("新手", 0, 200),
    ("可靠", 201, 500),
    ("优秀", 501, 800),
    ("大师", 801, 1000),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_reputation() -> dict:
    return load_json(REP_FILE)


def _save_reputation(data: dict):
    save_json(REP_FILE, data)


def _record_rep_event(agent_id: str, match_id: str, trace_ids: list[str],
                      score_before: float, score_after: float) -> dict:
    """Record a reputation change event (append-only, hash-chained, encrypted)."""
    # Load existing events from encrypted storage
    events = load_json("reputation_events.json")
    if not isinstance(events, list):
        events = []

    prev_hash = events[-1]["hash"] if events else "0" * 64

    event = {
        "event_id": f"revt-{uuid.uuid4().hex[:12]}",
        "agent_id": agent_id,
        "match_id": match_id,
        "trace_ids": trace_ids,
        "score_before": score_before,
        "score_after": score_after,
        "delta": round(score_after - score_before, 2),
        "timestamp": _now(),
        "prev_hash": prev_hash,
    }
    # Compute hash
    copy = {k: v for k, v in event.items() if k != "hash"}
    event["hash"] = hashlib.sha256(
        json.dumps(copy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    events.append(event)
    save_json("reputation_events.json", events)

    return event


def get_reputation(agent_id: str) -> dict:
    """Get current reputation for an agent."""
    reps = _load_reputation()
    if agent_id in reps:
        return reps[agent_id]

    # New agent starts at base reputation
    base = {
        "agent_id": agent_id,
        "score": 100.0,
        "tier": "新手",
        "total_matches": 0,
        "completed_matches": 0,
        "disputed_matches": 0,
        "cancelled_matches": 0,
        "average_rating": 0.0,
        "updated_at": _now(),
    }
    reps[agent_id] = base
    _save_reputation(reps)
    return base


def _get_tier(score: float) -> str:
    for name, lo, hi in TIERS:
        if lo <= score <= hi:
            return name
    return "新手"


def recalculate_reputation(agent_id: str) -> dict:
    """
    Full recalculation of reputation from match statuses + traces.
    Uses match-level outcomes (not just agent's own traces) for accuracy.
    
    Buyer reputation: agents who post needs and reliably verify/rate also earn reputation.
    """
    # Get all matches this agent participated in
    agent_matches = list_matches(agent_id=agent_id)

    total = len(agent_matches)
    completed = sum(1 for m in agent_matches if m["status"] == "completed")
    disputed = sum(1 for m in agent_matches if m["status"] == "disputed")
    cancelled = sum(1 for m in agent_matches if m["status"] == "cancelled")

    # Ratings this agent received (check ALL traces for their matches, not just their own)
    all_ratings = []
    buyer_actions = 0  # Count verify/rate actions (buyer reputation)
    for m in agent_matches:
        match_traces = get_traces_for_match(m["match_id"])
        for t in match_traces:
            # rate_partner from the OTHER party means this agent was rated (provider reputation)
            if t["action"] == "rate_partner" and "rating" in t.get("payload", {}):
                if t["agent_id"] != agent_id:
                    all_ratings.append(t["payload"]["rating"])
            # Count this agent's own verify/rate actions (buyer reputation)
            if t["action"] in ("verify_receipt", "rate_partner") and t["agent_id"] == agent_id:
                buyer_actions += 1

    avg_rating = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0.0

    # 🛡️ IQR outlier filtering: exclude extreme ratings
    filtered_ratings = all_ratings
    if len(all_ratings) >= 5:
        sorted_r = sorted(all_ratings)
        q1 = sorted_r[len(sorted_r)//4]
        q3 = sorted_r[3*len(sorted_r)//4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        filtered_ratings = [r for r in all_ratings if lower <= r <= upper]
        if len(filtered_ratings) >= 3:  # Keep at least 3 ratings
            avg_rating = round(sum(filtered_ratings) / len(filtered_ratings), 2)

    # Score calculation
    base = 100.0
    if total > 0:
        # Provider bonus: ratings received
        provider_bonus = (completed / total) * avg_rating * 100
        # Buyer bonus: being a good demand-side participant
        buyer_bonus = min((buyer_actions / max(total * 2, 1)) * 200, 200)
        completion_bonus = provider_bonus + buyer_bonus
    else:
        completion_bonus = 0

    penalty = 0
    if total > 0:
        penalty += (disputed / total) * 200
        penalty += (cancelled / total) * 100

    # Get current score for event recording
    current = get_reputation(agent_id)
    old_score = current["score"]

    new_score = max(0, min(1000, base + completion_bonus - penalty))
    new_score = round(new_score, 2)

    # Save
    reps = _load_reputation()
    reps[agent_id] = {
        "agent_id": agent_id,
        "score": new_score,
        "tier": _get_tier(new_score),
        "total_matches": total,
        "completed_matches": completed,
        "disputed_matches": disputed,
        "cancelled_matches": cancelled,
        "average_rating": avg_rating,
        "updated_at": _now(),
    }
    _save_reputation(reps)

    # Record event if score changed
    if old_score != new_score:
        agent_traces = get_traces_for_agent(agent_id, limit=10)
        trace_ids = [t["trace_id"] for t in agent_traces]
        _record_rep_event(agent_id, "recalc", trace_ids, old_score, new_score)

    return reps[agent_id]


def get_reputation_history(agent_id: str, limit: int = 20) -> list[dict]:
    """Get reputation change history for an agent."""
    events = load_json("reputation_events.json")
    if not isinstance(events, list):
        return []
    agent_events = [e for e in events if e.get("agent_id") == agent_id]
    return agent_events[-limit:]


def get_top_agents(limit: int = 10) -> list[dict]:
    """Get top agents by reputation score."""
    reps = _load_reputation()
    sorted_agents = sorted(reps.values(), key=lambda x: x["score"], reverse=True)
    return sorted_agents[:limit]
