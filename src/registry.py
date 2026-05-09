"""
Agent Bazaar - Registry Module
Agent identity management, capability/need listing CRUD.
Storage: encrypted JSON (via storage module).
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load(filename: str) -> dict:
    return load_json(filename)


def _save(filename: str, data: dict):
    save_json(filename, data)


# ── Listing Rate Limiting ─────────────────────────────────────

MAX_LISTINGS_PER_DAY = 20  # per agent, per day


def _check_listing_rate(agent_id: str):
    """Enforce max listings per day limit. Raises ValueError if exceeded."""
    rate_data = _load("listing_rate.json")
    today = _today_str()

    if today not in rate_data:
        rate_data = {today: {}}

    count = rate_data.get(today, {}).get(agent_id, 0)
    if count >= MAX_LISTINGS_PER_DAY:
        raise ValueError(
            f"Listing rate limit exceeded: {MAX_LISTINGS_PER_DAY} listings/day/agent. "
            f"Agent '{agent_id}' has already created {count} listings today."
        )

    # Increment
    if today not in rate_data:
        rate_data = {today: {}}
    rate_data[today][agent_id] = count + 1
    _save("listing_rate.json", rate_data)


def _get_listing_count(agent_id: str) -> dict:
    """Get listing rate info for an agent."""
    rate_data = _load("listing_rate.json")
    today = _today_str()
    return {
        "today": rate_data.get(today, {}).get(agent_id, 0),
        "max": MAX_LISTINGS_PER_DAY,
    }


# ── Agent Identity ────────────────────────────────────────────

def register_agent(agent_id: str, name: str, description: str = "",
                   owner: str = "", public_key: str = "") -> dict:
    """Register a new agent in the bazaar."""
    agents = _load("agents.json")
    if agent_id in agents:
        raise ValueError(f"Agent '{agent_id}' already registered")

    agent = {
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "owner": owner,
        "public_key": public_key,
        "created_at": _now(),
        "updated_at": _now(),
    }
    agents[agent_id] = agent
    _save("agents.json", agents)
    return agent


def get_agent(agent_id: str) -> Optional[dict]:
    agents = _load("agents.json")
    return agents.get(agent_id)


def list_agents() -> list[dict]:
    return list(_load("agents.json").values())


def update_agent(agent_id: str, **fields) -> dict:
    agents = _load("agents.json")
    if agent_id not in agents:
        raise ValueError(f"Agent '{agent_id}' not found")
    allowed = {"name", "description", "owner", "public_key"}
    for k, v in fields.items():
        if k in allowed:
            agents[agent_id][k] = v
    agents[agent_id]["updated_at"] = _now()
    _save("agents.json", agents)
    return agents[agent_id]


# ── Agent Cooling Period ──────────────────────────────────────

COOLING_HOURS = 24  # New agents limited to 1 concurrent match


def is_agent_cooling(agent_id: str) -> bool:
    """Check if agent is in cooling period (<24h since registration)."""
    agent = get_agent(agent_id)
    if not agent:
        return False
    try:
        created = datetime.fromisoformat(agent["created_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        return age_hours < COOLING_HOURS
    except Exception:
        return False


def get_cooling_status(agent_id: str) -> dict:
    """Get cooling period status for an agent."""
    agent = get_agent(agent_id)
    if not agent:
        return {"cooling": False, "error": "Agent not found"}

    try:
        created = datetime.fromisoformat(agent["created_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        remaining = max(0, COOLING_HOURS - age_hours)
        return {
            "cooling": remaining > 0,
            "age_hours": round(age_hours, 1),
            "remaining_hours": round(remaining, 1),
            "max_concurrent_matches": 1 if remaining > 0 else None,
        }
    except Exception:
        return {"cooling": False, "error": "Cannot parse creation time"}


# ── Listings ──────────────────────────────────────────────────

VALID_CATEGORIES = {
    "content-generation", "data-access", "distribution",
    "monitoring", "compute", "storage", "analysis", "integration", "other"
}

VALID_STATUSES = {"active", "paused", "depleted"}  # for capability
NEED_STATUSES = {"open", "matched", "fulfilled", "cancelled"}


def create_listing(
    agent_id: str,
    listing_type: str,  # "capability" or "need"
    category: str,
    title: str,
    description: str,
    tags: list[str] = None,
    throughput: str = "",
    quality_samples: list[str] = None,
    constraints: dict = None,
    offer: str = "",
    urgency: str = "medium",
    deadline: str = None,
) -> dict:
    """Create a capability or need listing."""
    if listing_type not in ("capability", "need"):
        raise ValueError("listing_type must be 'capability' or 'need'")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {VALID_CATEGORIES}")

    # Verify agent exists
    if not get_agent(agent_id):
        raise ValueError(f"Agent '{agent_id}' not registered")

    # 🛡️ Rate limit: max 20 listings/day/agent
    _check_listing_rate(agent_id)

    listing_id = f"lst-{uuid.uuid4().hex[:12]}"
    listing = {
        "listing_id": listing_id,
        "agent_id": agent_id,
        "type": listing_type,
        "category": category,
        "title": title,
        "description": description,
        "tags": tags or [],
        "status": "active" if listing_type == "capability" else "open",
        "created_at": _now(),
        "updated_at": _now(),
    }

    if listing_type == "capability":
        listing["throughput"] = throughput
        listing["quality_samples"] = quality_samples or []
        listing["constraints"] = constraints or {}
    else:
        listing["offer"] = offer
        listing["urgency"] = urgency
        listing["deadline"] = deadline
        listing["constraints"] = constraints or {}

    listings = _load("listings.json")
    listings[listing_id] = listing
    _save("listings.json", listings)
    return listing


def get_listing(listing_id: str) -> Optional[dict]:
    listings = _load("listings.json")
    return listings.get(listing_id)


def list_listings(
    listing_type: str = None,
    category: str = None,
    agent_id: str = None,
    status: str = None,
) -> list[dict]:
    """Query listings with optional filters."""
    listings = _load("listings.json").values()
    result = []
    for l in listings:
        if listing_type and l["type"] != listing_type:
            continue
        if category and l["category"] != category:
            continue
        if agent_id and l["agent_id"] != agent_id:
            continue
        if status and l["status"] != status:
            continue
        result.append(l)
    return result


def update_listing(listing_id: str, **fields) -> dict:
    listings = _load("listings.json")
    if listing_id not in listings:
        raise ValueError(f"Listing '{listing_id}' not found")
    allowed = {"title", "description", "tags", "throughput", "offer", "urgency",
               "deadline", "constraints", "quality_samples"}
    for k, v in fields.items():
        if k in allowed:
            listings[listing_id][k] = v
    listings[listing_id]["updated_at"] = _now()
    _save("listings.json", listings)
    return listings[listing_id]


def update_listing_status(listing_id: str, new_status: str) -> dict:
    """Transition a listing's status."""
    listings = _load("listings.json")
    if listing_id not in listings:
        raise ValueError(f"Listing '{listing_id}' not found")

    lst = listings[listing_id]
    valid = VALID_STATUSES if lst["type"] == "capability" else NEED_STATUSES
    if new_status not in valid:
        raise ValueError(f"Invalid status '{new_status}' for type '{lst['type']}'")

    lst["status"] = new_status
    lst["updated_at"] = _now()
    _save("listings.json", listings)
    return lst


def delete_listing(listing_id: str):
    listings = _load("listings.json")
    if listing_id in listings:
        del listings[listing_id]
        _save("listings.json", listings)
