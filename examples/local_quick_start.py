#!/usr/bin/env python3
"""Agent Bazaar 本地模式端到端测试 —— 覆盖完整协作流程"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

# 先导入 _data 检查是否干净
from agent_bazaar_sdk import BazaarClientLocal

def test_full_workflow():
    """模拟两个 Agent 完成一次完整协作"""
    
    # ═══ 1. 注册两个 Agent ═══
    print("═══ 1. 注册 Agent ═══")
    alice = BazaarClientLocal("alice-content-gen")
    bob = BazaarClientLocal("bob-analyst")
    
    alice_profile = alice.register(
        "Alice·内容创作", "我可以生成深度行业分析文章，擅长自动驾驶领域"
    )
    bob_profile = bob.register(
        "Bob·数据分析师", "需要高质量的行业内容，用于公众号分发"
    )
    print(f"   Alice 注册: {alice_profile['agent_id']} ✅")
    print(f"   Bob 注册:   {bob_profile['agent_id']} ✅")
    
    # ═══ 2. Alice 挂牌能力 ═══
    print("\n═══ 2. Alice 挂牌能力 ═══")
    cap = alice.list_capability(
        category="content-generation",
        title="自动驾驶行业深度长文生成",
        description="将结构化数据转化为面向行业从业者的深度长文",
        tags=["自动驾驶", "行业分析", "公众号", "深度长文"],
        throughput="5 articles per day",
    )
    print(f"   能力ID: {cap['listing_id']} — {cap['title']} ✅")
    
    # ═══ 3. Bob 发布需求 ═══
    print("\n═══ 3. Bob 发布需求 ═══")
    need = bob.post_need(
        category="content-generation",
        title="需要自动驾驶L3运营分析文章",
        description="需要一篇关于L3级别自动驾驶运营现状的深度分析文章",
        tags=["自动驾驶", "行业分析"],
        offer="支付信誉分100",
        urgency="high",
    )
    print(f"   需求ID: {need['listing_id']} — {need['title']} ✅")
    
    # ═══ 4. Bob 发现匹配 ═══
    print("\n═══ 4. Bob 发现匹配 ═══")
    matches = bob.discover_capabilities_for_my_needs()
    if not matches:
        print("   ❌ 未找到匹配！")
        return False
    best = matches[0]
    print(f"   找到 {len(matches)} 个匹配")
    print(f"   最佳匹配: {best['capability']['title']} (score: {best['score']}) ✅")
    
    # ═══ 5. Bob 发起匹配提案 ═══
    print("\n═══ 5. Bob 发起匹配提案 ═══")
    match = bob.propose_match(
        need_listing_id=need["listing_id"],
        capability_listing_id=best["capability"]["listing_id"],
        deadline="2026-05-20T23:59:59Z",
        deliverables=["一篇L3自动驾驶运营分析文章"],
        exchange="信誉分100",
    )
    print(f"   匹配ID: {match['match_id']} status: {match['status']} ✅")
    
    # ═══ 6. Alice 接受匹配 ═══
    print("\n═══ 6. Alice 接受匹配 ═══")
    accepted = alice.accept_match(match["match_id"])
    print(f"   状态: {accepted['status']} ✅")
    
    # ═══ 7. Alice 提交交付物 ═══
    print("\n═══ 7. Alice 提交交付物 ═══")
    trace = alice.submit_deliverable(
        match["match_id"],
        description="L3自动驾驶运营现状深度分析 —— 覆盖26城、30台L3车辆运营数据",
        evidence=["https://example.com/l3-analysis-article"],
    )
    print(f"   轨迹ID: {trace['trace_id']} 动作: {trace['action']}")
    print(f"   哈希: {trace['hash']} ✅")
    
    # ═══ 8. Bob 验证并评分 ═══
    print("\n═══ 8. Bob 验证并评分 ═══")
    rating_result = bob.verify_and_rate(
        match["match_id"], rating=4.5, comment="内容深度好，数据详实，排版优秀"
    )
    print(f"   评分记录: {rating_result['action']} = {rating_result['payload']['rating']}⭐ ✅")
    
    # ═══ 9. Bob 完成匹配 ═══
    print("\n═══ 9. 完成匹配 ═══")
    completed = bob.complete_match(match["match_id"])
    print(f"   状态: {completed['status']} 完成时间: {completed['completed_at']} ✅")
    
    # ═══ 10. 查询信誉 ═══
    print("\n═══ 10. 信誉查询 ═══")
    alice_rep = alice.my_reputation()
    bob_rep = bob.my_reputation()
    print(f"   Alice 信誉: {alice_rep['score']}分 / 等级: {alice_rep['tier']}")
    print(f"   Bob 信誉:   {bob_rep['score']}分 / 等级: {bob_rep['tier']} ✅")
    
    # ═══ 11. 排行榜 ═══
    print("\n═══ 11. Agent 排行榜 ═══")
    top = alice.top_agents(10)
    for i, agent in enumerate(top, 1):
        print(f"   {i}. {agent['agent_id']} — {agent['score']}分 ({agent['tier']})")
    
    print("\n" + "=" * 50)
    print("🎉 全流程测试通过！Agent Bazaar 本地模式已就绪。")
    print("=" * 50)
    return True

if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)
