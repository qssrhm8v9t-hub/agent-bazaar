"""Agent Bazaar 匹配引擎 — v0.1 规则引擎"""
import uuid
from datetime import datetime, timezone
try:
    from . import _data, registry, reputation
except ImportError:
    import _data, registry, reputation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _match_score(need: dict, capability: dict) -> float:
    """
    计算匹配分（协议 v0.1 规则引擎）

    匹配分 = 类别匹配(0.35) + 标签重叠(0.25) + 信誉门槛(0.20) + 时效性(0.20)
    """
    # 类别匹配 (0.35)
    cat_score = 1.0 if need["category"] == capability["category"] else 0.0

    # 标签重叠 (0.25)
    need_tags = set(need.get("tags", []))
    cap_tags = set(capability.get("tags", []))
    if need_tags:
        tag_score = len(need_tags & cap_tags) / max(len(need_tags), 1)
    else:
        tag_score = 0.5  # 需求方没写标签，不给标签拉偏架

    # 信誉门槛 (0.20) — 硬过滤
    min_rep = need.get("constraints", {}).get("min_reputation", 0)
    provider_rep = reputation.get_reputation(capability["agent_id"])["score"]
    rep_score = 1.0 if provider_rep >= min_rep else -1.0

    # 时效性 (0.20)
    try:
        updated = datetime.fromisoformat(capability["updated_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
        max_age = 720  # 30 天
        time_score = 1.0 - min(age_hours / max_age, 1.0)
    except Exception:
        time_score = 1.0

    return round(0.35 * cat_score + 0.25 * tag_score + 0.20 * rep_score + 0.20 * time_score, 4)


def discover_capabilities_for_need(need_id: str) -> list[dict]:
    """为需求发现匹配的能力挂牌。"""
    need = registry.get_listing(need_id)
    if not need:
        return []

    results = []
    for cap in _data.listings.values():
        if cap["type"] != "capability" or cap["status"] != "active":
            continue
        score = _match_score(need, cap)
        if score > 0:
            results.append({
                "capability": cap,
                "score": score,
                "listing_id": cap["listing_id"],
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def discover_needs_for_capability(cap_id: str) -> list[dict]:
    """为能力发现匹配的需求挂牌。"""
    cap = registry.get_listing(cap_id)
    if not cap:
        return []

    results = []
    for need in _data.listings.values():
        if need["type"] != "need" or need["status"] != "open":
            continue
        score = _match_score(need, cap)
        if score > 0:
            results.append({
                "need": need,
                "score": score,
                "listing_id": need["listing_id"],
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def propose_match(need_listing_id: str, capability_listing_id: str,
                  agent_id: str, deadline: str = None,
                  deliverables: list = None, exchange: str = "") -> dict:
    """需求方发起匹配提案。"""
    need = registry.get_listing(need_listing_id)
    cap = registry.get_listing(capability_listing_id)
    if not need:
        raise ValueError(f"Need '{need_listing_id}' 不存在")
    if not cap:
        raise ValueError(f"Capability '{capability_listing_id}' 不存在")
    if need["agent_id"] != agent_id:
        raise ValueError("只有需求方才能发起匹配提案")

    match_id = str(uuid.uuid4())[:8]
    match = {
        "match_id": match_id,
        "need_listing_id": need_listing_id,
        "capability_listing_id": capability_listing_id,
        "requester_agent_id": need["agent_id"],
        "provider_agent_id": cap["agent_id"],
        "status": "proposed",
        "terms": {
            "deadline": deadline or "",
            "deliverables": deliverables or [],
            "exchange": exchange,
        },
        "created_at": _now(),
        "completed_at": None,
    }
    _data.matches[match_id] = match
    return match


def bid_on_need(need_listing_id: str, capability_listing_id: str,
                agent_id: str, deadline: str = None,
                deliverables: list = None, exchange: str = "") -> dict:
    """能力方主动投标需求。"""
    cap = registry.get_listing(capability_listing_id)
    if not cap:
        raise ValueError(f"Capability '{capability_listing_id}' 不存在")
    if cap["agent_id"] != agent_id:
        raise ValueError("只能用自己的能力投标")

    need = registry.get_listing(need_listing_id)
    if not need:
        raise ValueError(f"Need '{need_listing_id}' 不存在")

    match_id = str(uuid.uuid4())[:8]
    match = {
        "match_id": match_id,
        "need_listing_id": need_listing_id,
        "capability_listing_id": capability_listing_id,
        "requester_agent_id": need["agent_id"],
        "provider_agent_id": agent_id,
        "status": "proposed",
        "terms": {
            "deadline": deadline or "",
            "deliverables": deliverables or [],
            "exchange": exchange,
        },
        "created_at": _now(),
        "completed_at": None,
    }
    _data.matches[match_id] = match
    return match


def accept_match(match_id: str, agent_id: str) -> dict:
    """接受匹配提案。"""
    if match_id not in _data.matches:
        raise KeyError(f"Match '{match_id}' 不存在")
    match = _data.matches[match_id]
    if agent_id not in (match["requester_agent_id"], match["provider_agent_id"]):
        raise ValueError("只有匹配参与方才能接受")
    match["status"] = "accepted"
    return match


def start_work(match_id: str, agent_id: str) -> dict:
    """服务方开始执行。"""
    if match_id not in _data.matches:
        raise KeyError(f"Match '{match_id}' 不存在")
    match = _data.matches[match_id]
    if agent_id != match["provider_agent_id"]:
        raise ValueError("只有服务方才能开始执行")
    match["status"] = "in_progress"
    return match


def complete_match(match_id: str, agent_id: str) -> dict:
    """完成匹配。"""
    if match_id not in _data.matches:
        raise KeyError(f"Match '{match_id}' 不存在")
    match = _data.matches[match_id]
    match["status"] = "completed"
    match["completed_at"] = _now()

    # 更新挂牌状态
    need = registry.get_listing(match["need_listing_id"])
    if need:
        need["status"] = "fulfilled"
    cap = registry.get_listing(match["capability_listing_id"])
    if cap:
        cap["status"] = "active"  # 能力可复用

    return match
