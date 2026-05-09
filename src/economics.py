"""
Agent Bazaar - Economics Module
Resource pricing market with reputation tiers, supply/demand adjustment,
and exchange rate discovery. Encrypted storage.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import load_json, save_json

try:
    from .reputation import get_reputation
except ImportError:
    from reputation import get_reputation

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(filename: str) -> dict:
    return load_json(filename)


def _save(filename: str, data: dict):
    save_json(filename, data)


# ── Resource Base Prices ──────────────────────────────────────

RESOURCE_BASE_PRICES = {
    "fresh_data_stream": 150,       # 实时数据流
    "structured_dataset": 120,      # 结构化数据集
    "longform_article": 100,        # 深度长文
    "social_media_thread": 60,      # 社交媒体图文
    "single_channel_distribution": 30,  # 单渠道分发
    "all_channel_distribution": 120,    # 全渠道分发
    "monitoring_daily_report": 80,  # 每日监测报告
    "strategy_analysis": 200,       # 战略分析报告
    "api_endpoint_access": 100,     # API接口访问
    "compute_hour": 50,             # 算力时
}

# Reputation tier multipliers
TIER_MULTIPLIERS = {
    "新手": 1.0,
    "可靠": 1.2,
    "优秀": 1.5,
    "大师": 2.0,
}


def get_price(resource_type: str, provider_agent_id: str = None,
              urgency: str = "medium") -> dict:
    """Get current market price for a resource type, adjusted by reputation and urgency."""
    base = RESOURCE_BASE_PRICES.get(resource_type, 50)
    
    # Reputation multiplier
    rep_mult = 1.0
    if provider_agent_id:
        rep = get_reputation(provider_agent_id)
        rep_mult = TIER_MULTIPLIERS.get(rep["tier"], 1.0)
    
    # Urgency multiplier
    urgency_mult = {"low": 0.8, "medium": 1.0, "high": 1.5, "critical": 2.5}
    urg_mult = urgency_mult.get(urgency, 1.0)
    
    # Supply/demand adjustment (simplified: count active listings)
    from registry import list_listings
    supply = len(list_listings(listing_type="capability", status="active"))
    demand = len(list_listings(listing_type="need", status="open"))
    sd_ratio = demand / max(supply, 1)
    sd_mult = 1.0 + (sd_ratio - 1.0) * 0.3  # ±30% based on supply/demand
    
    final_price = round(base * rep_mult * urg_mult * sd_mult, 2)
    
    return {
        "resource_type": resource_type,
        "base_price": base,
        "reputation_multiplier": rep_mult,
        "urgency_multiplier": urg_mult,
        "supply_demand_multiplier": round(sd_mult, 3),
        "supply": supply,
        "demand": demand,
        "final_price": final_price,
        "currency": "reputation_points",
    }


def get_market_snapshot() -> dict:
    """Get full market pricing snapshot."""
    from registry import list_listings
    
    supply = len(list_listings(listing_type="capability", status="active"))
    demand = len(list_listings(listing_type="need", status="open"))
    
    prices = {}
    for rt in RESOURCE_BASE_PRICES:
        prices[rt] = get_price(rt)
    
    return {
        "timestamp": _now(),
        "supply_count": supply,
        "demand_count": demand,
        "market_health": "buyers" if demand > supply else "balanced" if demand == supply else "sellers",
        "prices": prices,
    }


# ── Exchange Ledger ───────────────────────────────────────────

def record_exchange(payer_agent_id: str, receiver_agent_id: str,
                    amount: float, resource_type: str,
                    match_id: str, note: str = "") -> dict:
    """Record an economic exchange between agents."""
    exchange_id = f"xchg-{uuid.uuid4().hex[:12]}"
    exchange = {
        "exchange_id": exchange_id,
        "payer_agent_id": payer_agent_id,
        "receiver_agent_id": receiver_agent_id,
        "amount": amount,
        "resource_type": resource_type,
        "match_id": match_id,
        "note": note,
        "timestamp": _now(),
    }
    
    exchanges = _load("exchanges.json")
    exchanges[exchange_id] = exchange
    _save("exchanges.json", exchanges)
    return exchange


def get_agent_balance(agent_id: str) -> dict:
    """Calculate agent's economic balance (earned - spent)."""
    exchanges = _load("exchanges.json")
    earned = sum(e["amount"] for e in exchanges.values() 
                 if e["receiver_agent_id"] == agent_id)
    spent = sum(e["amount"] for e in exchanges.values() 
                if e["payer_agent_id"] == agent_id)
    tx_count = sum(1 for e in exchanges.values() 
                   if agent_id in (e["payer_agent_id"], e["receiver_agent_id"]))
    
    return {
        "agent_id": agent_id,
        "earned": round(earned, 2),
        "spent": round(spent, 2),
        "balance": round(earned - spent, 2),
        "transaction_count": tx_count,
    }


def get_exchange_history(agent_id: str = None, limit: int = 50) -> list[dict]:
    """Get exchange history."""
    exchanges = list(_load("exchanges.json").values())
    if agent_id:
        exchanges = [e for e in exchanges 
                     if agent_id in (e["payer_agent_id"], e["receiver_agent_id"])]
    exchanges.sort(key=lambda x: x["timestamp"], reverse=True)
    return exchanges[:limit]
