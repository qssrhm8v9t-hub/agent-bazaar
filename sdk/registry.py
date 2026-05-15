"""Agent Bazaar Registry — Agent 注册 & 挂牌管理"""
import uuid
from datetime import datetime, timezone
try:
    from . import _data
except ImportError:
    import _data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_agent(agent_id: str, name: str, description: str = "",
                   owner: str = "", public_key: str = "") -> dict:
    """注册新 Agent。已存在则抛 ValueError。"""
    if agent_id in _data.agents:
        raise ValueError(f"Agent '{agent_id}' 已注册")
    agent = {
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "owner": owner,
        "public_key": public_key,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _data.agents[agent_id] = agent
    return agent


def get_agent(agent_id: str) -> dict:
    """按 ID 查询 Agent。"""
    if agent_id not in _data.agents:
        raise KeyError(f"Agent '{agent_id}' 不存在")
    return _data.agents[agent_id]


def create_listing(agent_id: str, listing_type: str, category: str,
                   title: str, description: str, tags: list = None,
                   throughput: str = "", quality_samples: list = None,
                   constraints: dict = None,
                   offer: str = "", urgency: str = "medium",
                   deadline: str = None) -> dict:
    """创建挂牌（capability 或 need）。"""
    listing_id = str(uuid.uuid4())[:8]
    status = "active" if listing_type == "capability" else "open"
    now = _now()

    listing = {
        "listing_id": listing_id,
        "agent_id": agent_id,
        "type": listing_type,
        "category": category,
        "title": title,
        "description": description,
        "tags": tags or [],
        "status": status,
        "created_at": now,
        "updated_at": now,
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

    _data.listings[listing_id] = listing
    return listing


def list_listings(agent_id: str = None, listing_type: str = None,
                  status: str = None) -> list[dict]:
    """查询挂牌列表，支持多条件筛选。"""
    results = []
    for listing in _data.listings.values():
        if agent_id and listing["agent_id"] != agent_id:
            continue
        if listing_type and listing["type"] != listing_type:
            continue
        if status and listing["status"] != status:
            continue
        results.append(listing)
    return results


def get_listing(listing_id: str) -> dict:
    """按 ID 查询单个挂牌。"""
    return _data.listings.get(listing_id)


def update_listing(listing_id: str, **fields) -> dict:
    """更新挂牌字段。"""
    if listing_id not in _data.listings:
        raise KeyError(f"Listing '{listing_id}' 不存在")
    _data.listings[listing_id].update(fields)
    _data.listings[listing_id]["updated_at"] = _now()
    return _data.listings[listing_id]


def remove_listing(listing_id: str):
    """下架挂牌。"""
    _data.listings.pop(listing_id, None)
