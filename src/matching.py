"""
Agent Bazaar - Matching Engine
Rule-based matching between needs and capabilities.
v0.1: category + tag overlap + reputation threshold + recency.
Security: anti-self-dealing, new-agent cooling period (24h).
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import load_json, save_json
from registry import (get_agent, get_listing, list_listings, update_listing_status,
                       is_agent_cooling)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(filename: str) -> dict:
    return load_json(filename)


def _save(filename: str, data: dict):
    save_json(filename, data)


def _get_reputation(agent_id: str) -> float:
    """Get agent's current reputation score (default 100 for new agents)."""
    reps = _load("reputation.json")
    agent_rep = reps.get(agent_id, {})
    return agent_rep.get("score", 100.0)


def _count_active_matches(agent_id: str) -> int:
    """Count active (non-completed, non-cancelled) matches for an agent."""
    matches = _load("matches.json")
    active = 0
    for m in matches.values():
        if m["status"] in ("completed", "cancelled"):
            continue
        if agent_id in (m.get("requester_agent_id", ""), m.get("provider_agent_id", "")):
            active += 1
    return active


# ── Match Scoring ─────────────────────────────────────────────

def _score_match(need: dict, capability: dict) -> dict:
    """
    Score a potential match between a need and a capability.
    Returns {score, breakdown, pass_filter}.
    """
    # Category match (0.35 weight)
    cat_score = 1.0 if need["category"] == capability["category"] else 0.0

    # Tag overlap (0.25 weight)
    need_tags = set(need.get("tags", []))
    cap_tags = set(capability.get("tags", []))
    if need_tags:
        tag_score = len(need_tags & cap_tags) / max(len(need_tags), 1)
    else:
        tag_score = 0.5  # neutral if no tags specified

    # Reputation filter (0.20 weight, hard filter)
    min_rep = need.get("constraints", {}).get("min_reputation", 0)
    provider_rep = _get_reputation(capability["agent_id"])
    rep_pass = provider_rep >= min_rep
    rep_score = min(provider_rep / 1000.0, 1.0) if rep_pass else -1.0

    # Recency (0.20 weight)
    try:
        updated = datetime.fromisoformat(capability["updated_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
        recency_score = max(0, 1.0 - age_hours / (7 * 24))  # decays over 7 days
    except Exception:
        recency_score = 0.5

    # Weighted total
    weights = {"category": 0.35, "tag": 0.25, "reputation": 0.20, "recency": 0.20}
    if rep_score < 0:
        total = -1.0  # hard fail
    else:
        total = (
            cat_score * weights["category"]
            + tag_score * weights["tag"]
            + rep_score * weights["reputation"]
            + recency_score * weights["recency"]
        )

    return {
        "score": round(total, 4),
        "pass_filter": rep_pass and total >= 0,
        "breakdown": {
            "category": {"score": cat_score, "weight": weights["category"]},
            "tag_overlap": {"score": round(tag_score, 4), "weight": weights["tag"]},
            "reputation": {"score": round(rep_score, 4), "weight": weights["reputation"],
                           "provider_reputation": provider_rep, "min_required": min_rep},
            "recency": {"score": round(recency_score, 4), "weight": weights["recency"]},
        }
    }


# ── Discovery ─────────────────────────────────────────────────

def discover_capabilities_for_need(need_id: str, top_k: int = 10) -> list[dict]:
    """Given a need listing, find matching capabilities."""
    need = get_listing(need_id)
    if not need or need["type"] != "need":
        raise ValueError(f"Need listing '{need_id}' not found")
    if need["status"] != "open":
        return []

    capabilities = list_listings(listing_type="capability", status="active")
    scored = []
    for cap in capabilities:
        result = _score_match(need, cap)
        result["capability"] = cap
        scored.append(result)

    # Filter hard-fails, sort by score desc
    passed = [s for s in scored if s["pass_filter"]]
    passed.sort(key=lambda x: x["score"], reverse=True)
    return passed[:top_k]


def discover_needs_for_capability(cap_id: str, top_k: int = 10) -> list[dict]:
    """Given a capability listing, find matching needs."""
    cap = get_listing(cap_id)
    if not cap or cap["type"] != "capability":
        raise ValueError(f"Capability listing '{cap_id}' not found")
    if cap["status"] != "active":
        return []

    needs = list_listings(listing_type="need", status="open")
    scored = []
    for need in needs:
        result = _score_match(need, cap)
        result["need"] = need
        scored.append(result)

    passed = [s for s in scored if s["pass_filter"]]
    passed.sort(key=lambda x: x["score"], reverse=True)
    return passed[:top_k]


# ── Match Management ──────────────────────────────────────────

MATCH_STATUSES = {"proposed", "accepted", "in_progress", "completed", "disputed", "cancelled"}


def propose_match(need_listing_id: str, capability_listing_id: str,
                  requester_agent_id: str, deadline: str = None,
                  deliverables: list[str] = None, exchange: str = "") -> dict:
    """Create a match proposal. The requester_agent_id must own the need listing."""
    need = get_listing(need_listing_id)
    cap = get_listing(capability_listing_id)

    if not need or need["type"] != "need":
        raise ValueError(f"Invalid need listing '{need_listing_id}'")
    if not cap or cap["type"] != "capability":
        raise ValueError(f"Invalid capability listing '{capability_listing_id}'")
    if need["status"] != "open":
        raise ValueError(f"Need listing is not open (status: {need['status']})")
    if cap["status"] != "active":
        raise ValueError(f"Capability listing is not active (status: {cap['status']})")

    # Verify requester owns the need
    if requester_agent_id != need["agent_id"]:
        raise ValueError(f"Agent '{requester_agent_id}' does not own need '{need_listing_id}'")

    # 🛡️ Anti-self-dealing: prevent agent from trading with itself
    if need["agent_id"] == cap["agent_id"]:
        raise ValueError("Self-dealing is not allowed: need and capability belong to the same agent")

    # 🛡️ Cooling period: new agents limited to 1 concurrent match
    provider_id = cap["agent_id"]
    for agent in (requester_agent_id, provider_id):
        if is_agent_cooling(agent):
            active = _count_active_matches(agent)
            if active >= 1:
                from registry import get_cooling_status
                status = get_cooling_status(agent)
                raise ValueError(
                    f"Cooling period active: Agent '{agent}' is {status['age_hours']}h old "
                    f"({status['remaining_hours']}h remaining). Max 1 concurrent match during first 24h."
                )

    return _create_match(need_listing_id, capability_listing_id,
                         requester_agent_id, deadline, deliverables, exchange)


def bid_on_need(need_listing_id: str, capability_listing_id: str,
                provider_agent_id: str, deadline: str = None,
                deliverables: list[str] = None, exchange: str = "") -> dict:
    """Capability owner bids on someone else's need. The provider must own the capability."""
    need = get_listing(need_listing_id)
    cap = get_listing(capability_listing_id)

    if not need or need["type"] != "need":
        raise ValueError(f"Invalid need listing '{need_listing_id}'")
    if not cap or cap["type"] != "capability":
        raise ValueError(f"Invalid capability listing '{capability_listing_id}'")
    if need["status"] != "open":
        raise ValueError(f"Need listing is not open (status: {need['status']})")
    if cap["status"] != "active":
        raise ValueError(f"Capability listing is not active (status: {cap['status']})")

    # Verify provider owns the capability
    if provider_agent_id != cap["agent_id"]:
        raise ValueError(f"Agent '{provider_agent_id}' does not own capability '{capability_listing_id}'")

    # 🛡️ Anti-self-dealing
    if need["agent_id"] == cap["agent_id"]:
        raise ValueError("Self-dealing is not allowed: need and capability belong to the same agent")

    # 🛡️ Cooling period check
    if is_agent_cooling(provider_agent_id):
        active = _count_active_matches(provider_agent_id)
        if active >= 1:
            from registry import get_cooling_status
            status = get_cooling_status(provider_agent_id)
            raise ValueError(
                f"Cooling period active: Agent '{provider_agent_id}' is {status['age_hours']}h old "
                f"({status['remaining_hours']}h remaining). Max 1 concurrent match during first 24h."
            )

    # The need owner becomes the requester
    return _create_match(need_listing_id, capability_listing_id,
                         need["agent_id"], deadline, deliverables, exchange)


def _create_match(need_listing_id: str, capability_listing_id: str,
                  requester_agent_id: str, deadline: str = None,
                  deliverables: list[str] = None, exchange: str = "") -> dict:
    """Internal: create a match record."""
    need = get_listing(need_listing_id)
    cap = get_listing(capability_listing_id)

    match_id = f"match-{uuid.uuid4().hex[:12]}"
    match = {
        "match_id": match_id,
        "need_listing_id": need_listing_id,
        "capability_listing_id": capability_listing_id,
        "requester_agent_id": requester_agent_id,
        "provider_agent_id": cap["agent_id"],
        "status": "proposed",
        "terms": {
            "deadline": deadline,
            "deliverables": deliverables or [],
            "exchange": exchange or need.get("offer", ""),
        },
        "signatures": {"requester": "", "provider": ""},
        "created_at": _now(),
        "completed_at": None,
    }

    matches = _load("matches.json")
    matches[match_id] = match
    _save("matches.json", matches)

    # Update need status to "matched"
    update_listing_status(need_listing_id, "matched")

    return match


def accept_match(match_id: str, agent_id: str, signature: str = "") -> dict:
    """Provider accepts a proposed match."""
    matches = _load("matches.json")
    if match_id not in matches:
        raise ValueError(f"Match '{match_id}' not found")

    match = matches[match_id]
    if match["status"] != "proposed":
        raise ValueError(f"Match is not in 'proposed' status")
    if agent_id != match["provider_agent_id"]:
        raise ValueError(f"Only provider '{match['provider_agent_id']}' can accept")

    match["status"] = "accepted"
    match["signatures"]["provider"] = signature or f"signed-by-{agent_id}-{uuid.uuid4().hex[:8]}"
    _save("matches.json", matches)
    return match


def start_work(match_id: str, agent_id: str) -> dict:
    """Transition match to in_progress (idempotent)."""
    matches = _load("matches.json")
    match = matches[match_id]
    if match["status"] == "in_progress":
        return match  # already started
    if match["status"] != "accepted":
        raise ValueError(f"Match not accepted (status: {match['status']})")
    if agent_id != match["provider_agent_id"]:
        raise ValueError("Only provider can start work")

    match["status"] = "in_progress"
    _save("matches.json", matches)
    return match


def complete_match(match_id: str, agent_id: str) -> dict:
    """Mark match as completed (requester confirms)."""
    matches = _load("matches.json")
    match = matches[match_id]
    if match["status"] != "in_progress":
        raise ValueError(f"Match not in progress (status: {match['status']})")
    if agent_id != match["requester_agent_id"]:
        raise ValueError("Only requester can confirm completion")

    match["status"] = "completed"
    match["completed_at"] = _now()
    _save("matches.json", matches)

    # Free up listings
    update_listing_status(match["need_listing_id"], "fulfilled")
    # Capability stays active for future matches

    return match


def cancel_match(match_id: str, agent_id: str, reason: str = "") -> dict:
    """Cancel a match (either party can cancel before completion)."""
    matches = _load("matches.json")
    match = matches[match_id]
    if match["status"] in ("completed", "cancelled"):
        raise ValueError(f"Cannot cancel match in '{match['status']}' status")
    if agent_id not in (match["requester_agent_id"], match["provider_agent_id"]):
        raise ValueError("Only match participants can cancel")

    match["status"] = "cancelled"
    _save("matches.json", matches)

    # Reopen the need listing
    update_listing_status(match["need_listing_id"], "open")
    return match


def get_match(match_id: str) -> Optional[dict]:
    matches = _load("matches.json")
    return matches.get(match_id)


def list_matches(agent_id: str = None, status: str = None) -> list[dict]:
    matches = _load("matches.json").values()
    result = []
    for m in matches:
        if agent_id and agent_id not in (m["requester_agent_id"], m["provider_agent_id"]):
            continue
        if status and m["status"] != status:
            continue
        result.append(m)
    return result
