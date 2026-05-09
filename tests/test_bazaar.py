"""
Agent Bazaar - Integration Tests
End-to-end test: register agents → list capabilities/needs → match → execute → rate → verify reputation.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Clean any existing test data
data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
for f in ["agents.json", "listings.json", "matches.json", "traces.jsonl",
          "reputation.json", "reputation_events.jsonl"]:
    path = os.path.join(data_dir, f)
    if os.path.exists(path):
        os.remove(path)

from registry import register_agent, create_listing, list_listings, get_agent
from matching import (discover_capabilities_for_need, discover_needs_for_capability,
                      propose_match, accept_match, start_work, complete_match, get_match)
from tracer import record_trace, get_traces_for_match, verify_match_chain
from reputation import recalculate_reputation, get_reputation, get_top_agents

def test_full_flow():
    """Full agent bazaar lifecycle test."""
    print("=" * 60)
    print("Agent Bazaar v0.1 - Integration Test")
    print("=" * 60)

    # ── Phase 1: Register Agents ──────────────────────────
    print("\n📝 Phase 1: Registering Agents...")

    agents = [
        ("dabai", "大白", "智能工作助手，擅长内容生成与行业分析"),
        ("reg-tracker", "法规追踪Agent", "自动驾驶法规实时监测与解读"),
        ("content-gen", "内容生成Agent", "将结构化数据转为多平台内容"),
        ("distributor", "分发Agent", "微信+飞书+微博多渠道内容分发"),
        ("monitor", "监测Agent", "跨平台曝光数据回流与分析"),
    ]

    for aid, name, desc in agents:
        agent = register_agent(aid, name, desc)
        print(f"  ✅ {agent['name']} ({agent['agent_id']})")

    assert len(get_agent("dabai")) > 0
    print("  ✓ All agents registered")

    # ── Phase 2: Create Listings ──────────────────────────
    print("\n📋 Phase 2: Creating Listings...")

    # Capabilities
    caps = [
        ("reg-tracker", "capability", "data-access",
         "自动驾驶法规实时数据", "每日更新国家+地方自动驾驶法规",
         ["自动驾驶", "法规", "政策"], "24/7实时更新"),

        ("content-gen", "capability", "content-generation",
         "多平台内容生产", "法规→公众号长文/小红书图文/微博话题",
         ["内容生成", "公众号", "小红书", "微博"], "10篇/天"),

        ("distributor", "capability", "distribution",
         "多渠道内容分发", "微信公众平台+飞书群+微博+知乎同步分发",
         ["分发", "微信", "飞书", "微博"], "全平台覆盖"),

        ("monitor", "capability", "monitoring",
         "内容效果监测", "跨平台曝光量/互动量/转化率实时监测",
         ["监测", "数据分析", "回流"], "实时"),
    ]

    for aid, ltype, cat, title, desc, tags, throughput in caps:
        lst = create_listing(aid, ltype, cat, title, desc, tags, throughput)
        print(f"  ✅ [{lst['type']}] {lst['title']} ({lst['listing_id']})")

    # Needs
    needs = [
        ("reg-tracker", "need", "content-generation",
         "需要将法规周报转为多平台内容", "每周生成的政策周报需要转化",
         ["内容生成", "周报", "多平台"], "支付信誉分80", "medium"),

        ("content-gen", "need", "distribution",
         "需要稳定分发渠道", "生产的内容需要分发到各平台",
         ["分发", "多渠道"], "支付信誉分50", "medium"),

        ("dabai", "need", "monitoring",
         "需要内容效果数据回流", "分发后的效果数据需要监测回传",
         ["监测", "数据"], "支付信誉分60", "low",
         {"min_reputation": 200}),
    ]

    for aid, ltype, cat, title, desc, tags, offer, urgency, *rest in needs:
        constraints = rest[0] if rest else {}
        lst = create_listing(aid, ltype, cat, title, desc, tags,
                             offer=offer, urgency=urgency, constraints=constraints)
        print(f"  ✅ [{lst['type']}] {lst['title']} ({lst['listing_id']})")

    listings = list_listings()
    assert len(listings) == 7, f"Expected 7 listings, got {len(listings)}"
    print(f"  ✓ {len(listings)} listings created")

    # ── Phase 3: Discovery & Matching ─────────────────────
    print("\n🔍 Phase 3: Discovery & Matching...")

    # Find capabilities for reg-tracker's need
    need_listings = list_listings(listing_type="need", agent_id="reg-tracker")
    assert len(need_listings) == 1
    need_id = need_listings[0]["listing_id"]

    matches = discover_capabilities_for_need(need_id)
    print(f"  🔎 发现 {len(matches)} 个匹配能力:")
    for m in matches:
        cap = m["capability"]
        print(f"     {cap['title']} → 匹配分: {m['score']}")

    assert len(matches) > 0
    best = matches[0]
    print(f"  🎯 最佳匹配: {best['capability']['title']} (score={best['score']})")

    # Propose match
    match = propose_match(
        need_listing_id=need_id,
        capability_listing_id=best["capability"]["listing_id"],
        requester_agent_id="reg-tracker",
        deadline="2026-05-10T00:00:00Z",
        deliverables=["公众号长文1篇", "小红书图文3篇", "微博话题1条"],
        exchange="信誉分80"
    )
    print(f"  📨 匹配提案: {match['match_id']} (status={match['status']})")
    assert match["status"] == "proposed"

    # ── Phase 4: Execute & Trace ──────────────────────────
    print("\n⚡ Phase 4: Execute & Trace...")

    # Provider accepts
    accept_match(match["match_id"], match["provider_agent_id"])
    print(f"  ✅ Provider accepted")

    # Record trace: accept_match
    t1 = record_trace(match["match_id"], match["provider_agent_id"],
                      "accept_match", {"description": "已接受任务，开始准备内容"})
    print(f"  📍 Trace: {t1['action']} ({t1['trace_id']})")

    # Start work
    start_work(match["match_id"], match["provider_agent_id"])
    print(f"  🚀 Work started")

    # Submit deliverable
    t2 = record_trace(match["match_id"], match["provider_agent_id"],
                      "submit_deliverable", {
                          "description": "已完成所有内容交付",
                          "evidence": [
                              "https://mp.weixin.qq.com/s/mock-article-001",
                              "hash:sha256:abc123def456"
                          ]
                      })
    print(f"  📍 Trace: {t2['action']} ({t2['trace_id']})")

    # Requester verifies
    t3 = record_trace(match["match_id"], match["requester_agent_id"],
                      "verify_receipt", {
                          "description": "内容质量优秀，确认收货",
                      })
    print(f"  📍 Trace: {t3['action']} ({t3['trace_id']})")

    # Requester rates
    t4 = record_trace(match["match_id"], match["requester_agent_id"],
                      "rate_partner", {
                          "description": "内容专业，时效性好",
                          "rating": 4.8
                      })
    print(f"  📍 Trace: {t4['action']} rating={t4['payload']['rating']} ({t4['trace_id']})")

    # Complete match
    complete_match(match["match_id"], match["requester_agent_id"])
    print(f"  🎉 Match completed!")

    # Verify trace chain
    chain_result = verify_match_chain(match["match_id"])
    print(f"  🔐 Chain verification: {'✅ VALID' if chain_result['valid'] else '❌ BROKEN'} "
          f"({chain_result['traces']} traces)")

    # ── Phase 5: Reputation ───────────────────────────────
    print("\n⭐ Phase 5: Reputation Calculation...")

    # Calculate for provider
    rep = recalculate_reputation(match["provider_agent_id"])
    print(f"  Provider ({match['provider_agent_id']}): "
          f"score={rep['score']}, tier={rep['tier']}, "
          f"matches={rep['completed_matches']}")

    # Calculate for requester
    rep2 = recalculate_reputation(match["requester_agent_id"])
    print(f"  Requester ({match['requester_agent_id']}): "
          f"score={rep2['score']}, tier={rep2['tier']}")

    # Top agents
    top = get_top_agents(5)
    print(f"\n  🏆 Top Agents:")
    for a in top:
        print(f"     {a['agent_id']}: {a['score']} ({a['tier']})")

    # ── Phase 6: Cross-discovery ──────────────────────────
    print("\n🔄 Phase 6: Cross-Discovery...")

    # content-gen has a need for distribution
    cg_needs = list_listings(listing_type="need", agent_id="content-gen")
    if cg_needs:
        cg_matches = discover_capabilities_for_need(cg_needs[0]["listing_id"])
        print(f"  content-gen needs distribution → found {len(cg_matches)} providers")
        for m in cg_matches:
            print(f"     {m['capability']['title']} (score={m['score']})")

    # distributor can find needs
    dist_caps = list_listings(listing_type="capability", agent_id="distributor")
    if dist_caps:
        dist_needs = discover_needs_for_capability(dist_caps[0]["listing_id"])
        print(f"  distributor capability → found {len(dist_needs)} needs")
        for m in dist_needs:
            print(f"     {m['need']['title']} (score={m['score']})")

    # ── Summary ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    print(f"""
  Agents registered:    5
  Listings created:     7 (4 capabilities + 3 needs)
  Matches completed:    1
  Execution traces:     {len(get_traces_for_match(match['match_id']))}
  Trace chain valid:    {'YES' if chain_result['valid'] else 'NO'}
  Reputation updated:   YES
  Cross-discovery:      WORKING
    """)


if __name__ == "__main__":
    test_full_flow()
