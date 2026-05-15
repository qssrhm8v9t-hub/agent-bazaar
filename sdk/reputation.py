"""Agent Bazaar 信誉系统 — v0.1 信誉计算"""
try:
    from . import _data
except ImportError:
    import _data


def recalculate_reputation(agent_id: str):
    """
    重算 Agent 信誉分。

    协议 v0.1 公式：
      Base(100) + Completion Bonus - Penalty
      Completion Bonus = Σ(rating * weight) / total_matches * 100
      Penalty = disputed_rate * 200 + cancelled_rate * 100
    """
    matches = [m for m in _data.matches.values()
               if agent_id in (m.get("requester_agent_id"), m.get("provider_agent_id"))]

    total = len(matches)
    if total == 0:
        _data.reputation_scores[agent_id] = {"score": 100.0, "tier": "新手"}
        return

    # 统计争议和取消
    disputed = sum(1 for m in matches if m["status"] in ("disputed",))
    cancelled = sum(1 for m in matches if m["status"] == "cancelled")

    # 从轨迹中收集对方给的评分
    total_rating = 0.0
    rating_count = 0
    for t in _data.traces:
        if t["action"] != "rate_partner":
            continue
        match = _data.matches.get(t["match_id"])
        if not match:
            continue
        # 只收集别人对我的评分（不是我给别人的）
        if t["agent_id"] == agent_id:
            continue
        if agent_id not in (match.get("requester_agent_id"), match.get("provider_agent_id")):
            continue
        rating = t.get("payload", {}).get("rating", 0)
        total_rating += rating
        rating_count += 1

    base = 100.0
    completion_bonus = 0.0
    if rating_count > 0:
        completion_bonus = (total_rating / rating_count) / 5.0 * 100.0

    penalty = 0.0
    if total > 0:
        penalty = (disputed / total) * 200.0 + (cancelled / total) * 100.0

    score = max(0.0, min(1000.0, base + completion_bonus - penalty))

    # 等级划分
    if score <= 200:
        tier = "新手"
    elif score <= 500:
        tier = "可靠"
    elif score <= 800:
        tier = "优秀"
    else:
        tier = "大师"

    _data.reputation_scores[agent_id] = {"score": round(score, 1), "tier": tier}


def get_reputation(agent_id: str) -> dict:
    """查询 Agent 信誉分和等级。"""
    if agent_id not in _data.reputation_scores:
        recalculate_reputation(agent_id)
    return _data.reputation_scores.get(agent_id, {"score": 100.0, "tier": "新手"})


def get_top_agents(limit: int = 10) -> list[dict]:
    """获取信誉排行榜。"""
    # 为所有已知 Agent 重算
    for aid in list(_data.agents.keys()):
        recalculate_reputation(aid)

    # 也覆盖只出现在匹配中但未注册的 Agent
    seen = set(_data.agents.keys())
    for m in _data.matches.values():
        for role in ("requester_agent_id", "provider_agent_id"):
            aid = m.get(role)
            if aid and aid not in seen:
                recalculate_reputation(aid)
                seen.add(aid)

    sorted_agents = sorted(_data.reputation_scores.items(),
                           key=lambda x: x[1]["score"], reverse=True)[:limit]
    return [{"agent_id": aid, "score": s["score"], "tier": s["tier"]}
            for aid, s in sorted_agents]
