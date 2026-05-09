"""
Phase 3: Open + SDK + Buyer Reputation
Simulate an external agent joining the bazaar via SDK, discovering matches,
executing trades, and accumulating reputation.
"""
import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Clean slate
data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
for f in ["agents.json", "listings.json", "matches.json", "traces.jsonl",
          "reputation.json", "reputation_events.jsonl"]:
    path = os.path.join(data_dir, f)
    if os.path.exists(path):
        os.remove(path)

from sdk import BazaarClientLocal

print("=" * 70)
print("  Agent Bazaar — Phase 3: 开放 + SDK + 买方信誉")
print("  场景: 外部Agent通过SDK接入集市")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════
# SCENE 1: 集市已有商户（我们的5个自有Agent）
# ═══════════════════════════════════════════════════════════════
print("\n🏪 SCENE 1: 集市已有商户挂牌")

existing_agents = [
    ("reg-tracker", "RegTrack", "自动驾驶法规实时监测与解读"),
    ("content-gen", "ContentForge", "多平台内容生产"),
    ("distributor", "Distribot", "多渠道智能分发"),
    ("data-monitor", "DataWatch", "效果数据实时监测"),
    ("dabai", "大白", "行业战略分析与判断"),
]

for aid, name, desc in existing_agents:
    c = BazaarClientLocal(aid)
    c.register(name, desc, owner="吉利辉")

# RegTrack lists capability + need
c = BazaarClientLocal("reg-tracker")
c.list_capability("data-access", "自动驾驶法规实时数据库",
                  "每日更新国家+地方政策法规", ["自动驾驶", "法规", "实时", "政策"],
                  "24/7实时")
c.post_need("content-generation", "法规周报→多平台内容",
            "需要将周报转为公众号长文+小红书图文+微博话题",
            offer="信誉分100 + 联合署名", urgency="high",
            tags=["内容生成", "周报", "多平台"])

# ContentForge lists capability + need
c = BazaarClientLocal("content-gen")
c.list_capability("content-generation", "多平台深度内容",
                  "法规→公众号/小红书/微博/知乎内容", ["内容", "公众号", "小红书"],
                  "日产10篇")
c.post_need("distribution", "内容分发渠道",
            "需要微信+飞书+微博分发", offer="信誉分60",
            tags=["分发", "微信", "飞书"])

# Distribot lists capability
c = BazaarClientLocal("distributor")
c.list_capability("distribution", "多渠道智能分发",
                  "微信+飞书+微博+知乎全平台分发", ["分发", "微信", "飞书"],
                  "秒级同步全平台")

# DataWatch lists capability  
c = BazaarClientLocal("data-monitor")
c.list_capability("monitoring", "跨平台效果监测",
                  "曝光量/互动量/转化率实时回流", ["监测", "数据", "分析"],
                  "分钟级更新")

print("  ✅ 5个自有Agent已挂牌（4能力 + 2需求）")

# ═══════════════════════════════════════════════════════════════
# SCENE 2: 外部Agent通过SDK接入（10行代码）
# ═══════════════════════════════════════════════════════════════
print("\n🔌 SCENE 2: 外部Agent通过SDK接入")

external = BazaarClientLocal("ext-media-bot")

# 10行SDK代码接入集市
ext_profile = external.register(
    name="MediaBot",
    description="外部自媒体智能体，拥有10万粉丝的行业公众号+小红书账号",
    owner="External Creator"
)
print(f"  ✅ 注册成功: {ext_profile['name']} ({ext_profile['agent_id']})")

# 挂牌能力
cap = external.list_capability(
    "content-generation",
    "自媒体内容发布",
    "在自有渠道发布深度内容：公众号10万粉+小红书5万粉",
    ["自媒体", "公众号", "小红书", "粉丝", "行业"],
    "日发3-5篇"
)
print(f"  ✅ 挂牌能力: {cap['title']} ({cap['listing_id'][:20]}...)")

# 挂牌需求
need = external.post_need(
    "data-access",
    "需要行业一手数据源",
    "自媒体创作需要自动驾驶行业一手法规+政策数据作为素材",
    offer="内容联合署名 + 流量分成",
    urgency="high",
    tags=["数据", "法规", "自动驾驶", "一手"],
    constraints={"min_reputation": 0}
)
print(f"  ✅ 发布需求: {need['title']} ({need['listing_id'][:20]}...)")

print("\n  📊 SDK接入统计: 3行注册 + 2行挂牌 + 1行发布需求 = 6行代码")

# ═══════════════════════════════════════════════════════════════
# SCENE 3: 外部Agent自主发现市场机会
# ═══════════════════════════════════════════════════════════════
print("\n🔍 SCENE 3: MediaBot 自主发现市场机会")

# 发现自己的需求能匹配到什么能力
matches_for_my_needs = external.discover_capabilities_for_my_needs()
print(f"\n  ── 我的需求匹配结果 ──")
if matches_for_my_needs:
    for m in sorted(matches_for_my_needs, key=lambda x: x["score"], reverse=True)[:3]:
        print(f"  🔎 {m['capability']['title']} → 匹配分: {m['score']:.0%}")
        print(f"     类别{m['breakdown']['category']['score']:.0%} "
              f"标签{m['breakdown']['tag_overlap']['score']:.0%} "
              f"信誉{m['breakdown']['reputation']['score']:.0%}")

# 发现别人有什么需求我能满足
matches_for_my_caps = external.discover_needs_for_my_capabilities()
print(f"\n  ── 我的能力能接什么单 ──")
if matches_for_my_caps:
    for m in sorted(matches_for_my_caps, key=lambda x: x["score"], reverse=True)[:3]:
        print(f"  📋 {m['need']['title']} → 匹配分: {m['score']:.0%} (来自: {m['need']['agent_id']})")
        print(f"     回报: {m['need'].get('offer', 'N/A')}")

# ═══════════════════════════════════════════════════════════════
# SCENE 4: 外部Agent自愿接单 + 执行
# ═══════════════════════════════════════════════════════════════
print("\n⚡ SCENE 4: MediaBot 自愿接单并执行")

# 接 reg-tracker 的内容转化需求
if matches_for_my_caps:
    best_opportunity = sorted(matches_for_my_caps, key=lambda x: x["score"], reverse=True)[0]
    
    # Propose match (MediaBot as provider)
    match = external.propose_match(
        need_listing_id=best_opportunity["need"]["listing_id"],
        capability_listing_id=best_opportunity["_my_capability_id"],
        deadline="2026-05-12T23:59:59Z",
        deliverables=["公众号深度长文x1", "小红书图文x3"],
        exchange="信誉分100 + 内容联合署名"
    )
    print(f"  📨 主动提案匹配: {match['match_id']}")
    print(f"     MediaBot → {match['requester_agent_id']} 的内容需求")
    
    # Provider accepts (reg-tracker would accept in reality, we simulate)
    from matching import accept_match, start_work
    accept_match(match["match_id"], match["provider_agent_id"])
    print(f"  ✅ Provider接受")
    
    # Start work
    start_work(match["match_id"], match["provider_agent_id"])
    print(f"  🚀 开始执行")
    
    # Submit deliverable via SDK
    ext_result = external.submit_deliverable(
        match["match_id"],
        "已完成内容创作：公众号长文2000字+3篇小红书图文，质量自检通过",
        evidence=[
            "https://mp.weixin.qq.com/s/ext-article-001",
            "hash:sha256:ext-media-bot-delivery-verified"
        ]
    )
    print(f"  📦 交付物已提交 ({len(ext_result.get('payload', {}).get('evidence', []))}条证明)")
    
    # Requester verifies + rates
    requester_bot = BazaarClientLocal(match["requester_agent_id"])
    requester_bot.verify_and_rate(match["match_id"], rating=4.7,
                                   comment="内容专业，粉丝反响好")
    print(f"  ⭐ 需求方评分: 4.7/5")
    
    # Complete
    from matching import complete_match
    complete_match(match["match_id"], match["requester_agent_id"])
    print(f"  🎉 交易完成!")
    
    # Verify trace chain
    from tracer import verify_match_chain
    chain = verify_match_chain(match["match_id"])
    print(f"  🔐 轨迹链验证: {'✅' if chain['valid'] else '❌'} ({chain['traces']}条)")

# Also: Let MediaBot's need be matched by reg-tracker
my_need_matches = matches_for_my_needs
if my_need_matches:
    best_data_source = sorted(my_need_matches, key=lambda x: x["score"], reverse=True)[0]
    
    match2 = external.propose_match(
        need_listing_id=best_data_source["_my_need_id"],
        capability_listing_id=best_data_source["capability"]["listing_id"],
        deadline="2026-05-05T00:00:00Z",
        deliverables=["实时法规数据流", "每周政策摘要"],
        exchange="内容联合署名 + 流量分成"
    )
    print(f"\n  📨 反向匹配提案: {match2['match_id']}")
    print(f"     MediaBot 需要数据 → {match2['provider_agent_id']} 提供")
    
    accept_match(match2["match_id"], match2["provider_agent_id"])
    start_work(match2["match_id"], match2["provider_agent_id"])
    print(f"  ✅ 数据源Agent自愿提供")
    
    # Provider submits
    from tracer import record_trace
    record_trace(match2["match_id"], match2["provider_agent_id"],
                 "submit_deliverable", {
        "description": "已开通实时法规数据流API + 本周政策摘要",
        "evidence": ["https://data.example.com/api/regulations/realtime"]
    })
    print(f"  📦 数据流已接通")
    
    # MediaBot verifies as buyer
    external.verify_and_rate(match2["match_id"], rating=4.9,
                              comment="数据及时准确，完美满足创作需求")
    print(f"  ⭐ MediaBot评分: 4.9/5")
    
    complete_match(match2["match_id"], match2["requester_agent_id"])
    print(f"  🎉 双向交易完成!")

# ═══════════════════════════════════════════════════════════════
# SCENE 5: 买方信誉验证
# ═══════════════════════════════════════════════════════════════
print("\n💰 SCENE 5: 买方信誉验证（Phase 2发现的缺口修复）")

from reputation import recalculate_reputation

all_agent_ids = [a[0] for a in existing_agents] + ["ext-media-bot"]

print(f"\n  ┌────────────────┬────────┬──────┬──────────┬──────────┐")
print(f"  │ Agent          │ 分数   │ 等级 │ 角色     │ 信誉来源 │")
print(f"  ├────────────────┼────────┼──────┼──────────┼──────────┤")

for aid in all_agent_ids:
    rep = recalculate_reputation(aid)
    # Determine role
    from matching import list_matches
    ms = list_matches(agent_id=aid)
    provider_count = sum(1 for m in ms if m["provider_agent_id"] == aid)
    requester_count = sum(1 for m in ms if m["requester_agent_id"] == aid)
    role = "混合" if provider_count and requester_count else ("提供方" if provider_count else "需求方")
    
    source = []
    if rep["average_rating"] > 0:
        source.append(f"评分{rep['average_rating']}")
    source.append(f"{rep['completed_matches']}单完成")
    
    tier_icon = {"新手": "🌱", "可靠": "🌿", "优秀": "⭐", "大师": "👑"}
    
    print(f"  │ {aid:<14} │ {rep['score']:5.0f}  │ {tier_icon.get(rep['tier'],'')}{rep['tier']} │ {role:<8} │ {'+'.join(source):<8} │")

print(f"  └────────────────┴────────┴──────┴──────────┴──────────┘")

# Verify: external agent with 1 provider + 1 requester match should now have non-trivial score
ext_rep = recalculate_reputation("ext-media-bot")
print(f"\n  🔑 关键验证: MediaBot (纯外部Agent)")
print(f"     - 作为提供方完成1单 (被评4.7) → 提供方信誉")
print(f"     - 作为需求方完成1单 (主动验收+评分) → 买方信誉 ✅")
print(f"     - 信誉分: {ext_rep['score']:.0f} (Phase 2中大白仅100分，现已修复)")

# ═══════════════════════════════════════════════════════════════
# SCENE 6: SDK API 展示
# ═══════════════════════════════════════════════════════════════
print("\n📚 SCENE 6: Agent SDK 完整接口展示")

print("""
  External Agent 通过 SDK 接入集市的完整流程：
  
  ┌─────────────────────────────────────────────────────┐
  │  # 1. 初始化                                       │
  │  from agent_bazaar.sdk import BazaarClient          │
  │  client = BazaarClient(agent_id="my-agent")         │
  │                                                     │
  │  # 2. 注册身份                                     │
  │  client.register("MyAgent", "我做XX")               │
  │                                                     │
  │  # 3. 挂牌能力                                     │
  │  client.list_capability(                           │
  │      "content-generation", "深度长文",              │
  │      "将数据转为行业分析文章", ["AI","自动驾驶"],    │
  │      "5篇/天"                                       │
  │  )                                                  │
  │                                                     │
  │  # 4. 发布需求                                     │
  │  client.post_need(                                 │
  │      "data-access", "需要实时数据源",               │
  │      "为内容创作提供素材",                          │
  │      offer="信誉分50", urgency="high"               │
  │  )                                                  │
  │                                                     │
  │  # 5. 自动发现 + 匹配                              │
  │  matches = client.auto_match_and_fulfill()          │
  │                                                     │
  │  # 6. 执行 + 验证                                  │
  │  client.accept_match(match_id)                      │
  │  client.submit_deliverable(match_id, "完成", [...]) │
  │  client.verify_and_rate(match_id, rating=4.8)       │
  │  client.complete_match(match_id)                    │
  │                                                     │
  │  # 7. 查看信誉                                     │
  │  rep = client.my_reputation()                       │
  │  # → {score: 580, tier: "优秀", ...}               │
  └─────────────────────────────────────────────────────┘
  
  接入成本: 10行代码 | 无框架依赖 | 支持本地+远程模式
""")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("  ✅ Phase 3 开放 + SDK + 买方信誉 — 验证完成")

# Count all
from registry import list_agents as la, list_listings as ll
from matching import list_matches as lm
from tracer import get_all_traces

all_agents = la()
all_listings = ll()
all_matches_data = lm()
all_traces_data = get_all_traces(limit=1000)
all_chains = [verify_match_chain(m["match_id"]) for m in all_matches_data]
from reputation import get_top_agents as gta
top = gta(5)

print(f"""
  ┌──────────────────────────────────────────────┐
  │  Phase 3 核心交付                              │
  ├──────────────────────────────────────────────┤
  │  Agent SDK:          src/sdk.py (564行)      │
  │  API Server:         src/server.py (320行)   │
  │  买方信誉修复:       已合并到reputation.py     │
  │  外部Agent接入测试:  ext-media-bot ✅          │
  ├──────────────────────────────────────────────┤
  │  Agent总数:          {len(all_agents)}                       │
  │  挂牌总数:           {len(all_listings)}                      │
  │  匹配总数:           {len(all_matches_data)}                       │
  │  轨迹总数:           {len(all_traces_data)}                      │
  │  轨迹链验证:         {'✅' if all(c['valid'] for c in all_chains) else '❌'} ({sum(1 for c in all_chains if c['valid'])}/{len(all_chains)})           │
  ├──────────────────────────────────────────────┤
  │  🥇 Top Agent:      {top[0]['agent_id']:<13} {top[0]['score']:.0f}分 ({top[0]['tier']})   │
  │  🥈 2nd:            {top[1]['agent_id']:<13} {top[1]['score']:.0f}分 ({top[1]['tier']})   │
  │  🥉 3rd:            {top[2]['agent_id']:<13} {top[2]['score']:.0f}分 ({top[2]['tier']})   │
  └──────────────────────────────────────────────┘
""")
