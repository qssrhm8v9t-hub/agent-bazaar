"""Agent Bazaar — 共享内存数据存储（本地模式）"""
agents = {}              # agent_id → agent_dict
listings = {}            # listing_id → listing_dict
matches = {}             # match_id → match_dict
traces = []              # [trace_dict, ...] append-only
reputation_scores = {}   # agent_id → {"score": float, "tier": str}
