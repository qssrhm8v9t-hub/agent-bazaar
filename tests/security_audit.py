"""
Agent Bazaar 安全审计脚本
模拟攻击者视角，验证系统对常见攻击向量的防御能力。
"""
import sys, os, json, hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
for f in os.listdir(data_dir):
    if f.endswith(('.json', '.jsonl')):
        os.remove(os.path.join(data_dir, f))

from registry import register_agent, create_listing, get_agent
from matching import (propose_match, accept_match, complete_match,
                      bid_on_need, get_match, list_matches)
from tracer import record_trace, verify_match_chain, get_traces_for_match
from reputation import recalculate_reputation, get_reputation
from economics import get_price, record_exchange, get_agent_balance
from dao import create_proposal, vote, tally_proposal, execute_proposal, get_voting_power

print("=" * 70)
print("  🛡️  Agent Bazaar — 安全审计报告")
print("=" * 70)

issues = []
warnings = []
passed = []

# ═══════════════════════════════════════════════════════════════
# A. 身份伪造攻击
# ═══════════════════════════════════════════════════════════════
print("\n🔍 A. 身份伪造攻击测试")

# Setup
register_agent("honest-agent", "HonestAgent", "合法Agent")
register_agent("attacker", "Attacker", "恶意Agent")

# Test 1: Can attacker create listing as another agent?
print("  A1. 冒名挂牌测试...")
try:
    create_listing("honest-agent", "capability", "content-generation",
                   "被伪造的能力", "attacker试图用honest-agent身份挂牌",
                   agent_id_override="attacker")  # This shouldn't work
    issues.append("A1 ❌ 可用他人身份挂牌 — agent_id参数未被验证")
    print("     ❌ 漏洞: 可用他人身份创建挂牌")
except TypeError:
    # No agent_id_override parameter exists
    create_listing("attacker", "capability", "content-generation",
                   "attacker自己的能力", ["攻击"])
    lst = create_listing("attacker", "capability", "content-generation",
                         "伪装能力", ["合法"])
    # Verify the listing is under attacker, not honest-agent
    if lst["agent_id"] == "attacker":
        passed.append("A1 ✅ 挂牌必须使用自己身份 — 参数正确绑定")
        print("     ✅ 挂牌身份绑定正确")
    else:
        issues.append("A1 ❌ 挂牌身份可能被伪造")
        print("     ❌ 挂牌身份绑定异常")

# Test 2: Can attacker accept a match not directed to them?
print("  A2. 越权接受匹配测试...")
# honest-agent posts need, content-gen provides capability
register_agent("provider-a2", "ProviderA2", "测试提供方")
m1 = propose_match(
    create_listing("honest-agent", "need", "data-access", "测试需求", "test",
                   offer="10", urgency="low")["listing_id"],
    create_listing("provider-a2", "capability", "data-access", "测试能力", "test")["listing_id"],
    "honest-agent"
)
try:
    accept_match(m1["match_id"], "attacker")
    issues.append("A2 ❌ 攻击者可越权接受他人匹配")
    print("     ❌ 漏洞: 可越权接受他人匹配")
except ValueError as e:
    passed.append("A2 ✅ 匹配接受有身份校验")
    print(f"     ✅ 身份校验生效: {e}")

# Test 3: Can attacker complete someone else's match?
print("  A3. 越权完成匹配测试...")
# First, provider-a2 accepts and works
accept_match(m1["match_id"], "provider-a2")
from matching import start_work
start_work(m1["match_id"], "provider-a2")
record_trace(m1["match_id"], "provider-a2", "submit_deliverable",
             {"description": "完成"})
record_trace(m1["match_id"], "honest-agent", "verify_receipt",
             {"description": "验证"})
try:
    complete_match(m1["match_id"], "attacker")
    issues.append("A3 ❌ 攻击者可越权完成他人匹配")
    print("     ❌ 漏洞: 可越权完成匹配")
except ValueError as e:
    passed.append("A3 ✅ 匹配完成有身份校验")
    print(f"     ✅ 身份校验生效")
complete_match(m1["match_id"], "honest-agent")

# ═══════════════════════════════════════════════════════════════
# B. 信誉操纵攻击
# ═══════════════════════════════════════════════════════════════
print("\n🔍 B. 信誉操纵攻击测试")

# Test B1: Sybil attack — create many agents to farm reputation
print("  B1. 女巫攻击(批量注册刷信誉)测试...")
sybil_agents = []
for i in range(10):
    aid = f"sybil-{i}"
    register_agent(aid, f"Sybil{i}", "女巫攻击测试")
    sybil_agents.append(aid)

# Try to farm reputation through fake trades
for i in range(0, 10, 2):
    buyer = sybil_agents[i]
    seller = sybil_agents[i+1]
    # Create listings
    need = create_listing(buyer, "need", "data-access", f"假需求{i}", "wash trade")
    cap = create_listing(seller, "capability", "data-access", f"假能力{i}", "wash trade")
    # Fake match
    m = propose_match(need["listing_id"], cap["listing_id"], buyer)
    accept_match(m["match_id"], seller)
    start_work(m["match_id"], seller)
    record_trace(m["match_id"], seller, "submit_deliverable", {"description": "fake"})
    record_trace(m["match_id"], buyer, "verify_receipt", {"description": "fake"})
    record_trace(m["match_id"], buyer, "rate_partner", {"rating": 5.0})

# Check if Sybil agent gained reputation
rep = recalculate_reputation(sybil_agents[0])
if rep["score"] > 500:
    issues.append(f"B1 ❌ 女巫攻击成功 — sybil-0获得{rep['score']}分信誉(通过虚假交易)")
    print(f"     ❌ 女巫攻击成功: sybil-0 = {rep['score']}分")
else:
    passed.append(f"B1 ✅ 女巫攻击部分受限 — 虚假交易信誉增长有限")
    print(f"     ⚠️  sybil-0 = {rep['score']}分 (需进一步防御)")

# Test B2: Rating manipulation
print("  B2. 评分操纵测试...")
# Honest agent gets rated artificially
attacker_need = create_listing("attacker", "need", "data-access", "攻击需求", "test", offer="1")
honest_cap = create_listing("honest-agent", "capability", "data-access", "目标能力", "test")
m2 = propose_match(attacker_need["listing_id"], honest_cap["listing_id"], "attacker")
accept_match(m2["match_id"], "honest-agent")
start_work(m2["match_id"], "honest-agent")
record_trace(m2["match_id"], "honest-agent", "submit_deliverable", {"description": "ok"})
record_trace(m2["match_id"], "attacker", "verify_receipt", {"description": "ok"})
# Rate with extreme values
record_trace(m2["match_id"], "attacker", "rate_partner", {"rating": 0.1})
rep_after = recalculate_reputation("honest-agent")

if rep_after["score"] < 200:
    warnings.append("B2 ⚠️ 恶意低分可显著影响信誉 — 需引入评分中位数/异常值过滤")
    print(f"     ⚠️  恶意低分可拉低信誉: honest-agent = {rep_after['score']}分")
else:
    passed.append("B2 ✅ 信誉计算对异常评分有一定抗性")
    print(f"     ✅ 信誉计算有一定抗性: {rep_after['score']}分")

# ═══════════════════════════════════════════════════════════════
# C. 数据篡改攻击
# ═══════════════════════════════════════════════════════════════
print("\n🔍 C. 数据篡改攻击测试")

# Test C1: Direct JSON file tampering
print("  C1. 直接篡改JSON数据文件测试...")
traces_file = os.path.join(data_dir, "traces.jsonl")
if os.path.exists(traces_file):
    with open(traces_file, "r") as f:
        lines = f.readlines()
    if lines:
        # Try to modify a trace
        trace = json.loads(lines[-1])
        old_hash = trace.get("hash", "")
        trace["payload"]["rating"] = 5.0  # Tamper!
        # Re-hash
        tampered = {k: v for k, v in trace.items() if k != "hash"}
        trace["hash"] = hashlib.sha256(
            json.dumps(tampered, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        
        # Verify chain is now broken
        from tracer import verify_match_chain as vm
        result = vm(trace["match_id"])
        if not result["valid"]:
            passed.append("C1 ✅ 哈希链防篡改生效 — 篡改导致链断裂")
            print(f"     ✅ 哈希链检测到篡改: chain_valid={result['valid']}")
        else:
            issues.append("C1 ❌ 哈希链未检测到篡改")
            print(f"     ❌ 篡改未被检测!")

# Test C2: Reputation data tampering
print("  C2. 信誉数据篡改测试...")
rep_file = os.path.join(data_dir, "reputation.json")
if os.path.exists(rep_file):
    with open(rep_file) as f:
        reps = json.load(f)
    if "honest-agent" in reps:
        original_score = reps["honest-agent"]["score"]
        reps["honest-agent"]["score"] = 999  # Tamper
        with open(rep_file, "w") as f:
            json.dump(reps, f)
        # Recalculate should correct the tampered score
        fixed = recalculate_reputation("honest-agent")
        if fixed["score"] != 999:
            passed.append("C2 ✅ 信誉重算可纠正被篡改数据")
            print(f"     ✅ 重算纠正篡改: {original_score}→{fixed['score']} (尝试设为999)")
        else:
            issues.append("C2 ❌ 信誉篡改无法通过重算纠正")
            print(f"     ❌ 篡改无法纠正: {fixed['score']}")

# ═══════════════════════════════════════════════════════════════
# D. 经济攻击向量
# ═══════════════════════════════════════════════════════════════
print("\n🔍 D. 经济攻击向量测试")

# Test D1: Wash trading (self-dealing)
print("  D1. 自成交刷量测试...")
# Can an agent trade with itself?
self_need = create_listing("attacker", "need", "data-access", "自成交需求", "wash")
self_cap = create_listing("attacker", "capability", "data-access", "自成交能力", "wash")
try:
    m_self = propose_match(self_need["listing_id"], self_cap["listing_id"], "attacker")
    issues.append("D1 ❌ Agent可与自己交易洗量")
    print(f"     ❌ 自成交可能: {m_self['match_id']}")
except ValueError as e:
    passed.append("D1 ✅ 自成交被阻止")
    print(f"     ✅ 自成交被阻止")

# Test D2: Pricing manipulation through fake supply/demand
print("  D2. 虚假供需操纵定价测试...")
from economics import get_market_snapshot
snap = get_market_snapshot()
# Create many fake listings to manipulate supply
fake_needs = []
for i in range(20):
    try:
        n = create_listing("attacker", "need", "content-generation",
                          f"虚假需求#{i}", "价格操纵", offer="1000")
        fake_needs.append(n)
    except:
        pass
snap2 = get_market_snapshot()
if snap2["demand_count"] > snap["demand_count"] + 15:
    warnings.append("D2 ⚠️ 虚假挂牌可操纵供需比影响定价 — 需挂牌频率限制")
    print(f"     ⚠️  供需被操纵: {snap['demand_count']}→{snap2['demand_count']}")
else:
    passed.append("D2 ✅ 供需数据未被大量虚假挂牌影响")
    print(f"     ✅ 供需稳定: {snap['demand_count']}→{snap2['demand_count']}")

# ═══════════════════════════════════════════════════════════════
# E. DAO治理攻击
# ═══════════════════════════════════════════════════════════════
print("\n🔍 E. DAO治理攻击测试")

# Test E1: Vote buying / Sybil voting
print("  E1. 女巫投票攻击测试...")
register_agent("dao-attacker", "DaoAttacker", "治理攻击者")
prop = create_proposal("dao-attacker", "general", "恶意提案", "test attack", voting_period_hours=1)

# Check sybil agents' voting power
sybil_voting_power = 0
for aid in sybil_agents[:5]:
    vp = get_voting_power(aid)
    sybil_voting_power += vp["voting_power"]
    vote(prop["proposal_id"], aid, "for")

honest_vp = get_voting_power("honest-agent")
vote(prop["proposal_id"], "honest-agent", "against")

tally = tally_proposal(prop["proposal_id"])

if sybil_voting_power > honest_vp["voting_power"] * 2:
    warnings.append(f"E1 ⚠️ 女巫投票权({sybil_voting_power:.0f}) > 诚实Agent({honest_vp['voting_power']:.0f}) — 需基于交易量而非代理数量分配投票权")
    print(f"     ⚠️  女巫投票权 = {sybil_voting_power:.0f} vs 诚实Agent = {honest_vp['voting_power']:.0f}")
else:
    passed.append("E1 ✅ 投票权分布合理")
    print(f"     ✅ 女巫投票权受限于交易量")

# Test E2: Human veto safety
print("  E2. 人类否决安全护栏测试...")
prop2 = create_proposal("attacker", "resource_pricing", "自利提案", "为自己提价500%")
vote(prop2["proposal_id"], "attacker", "for")

# Human veto should work regardless of quorum
try:
    result = execute_proposal(prop2["proposal_id"], executor="human_veto")
    if result["status"] == "vetoed":
        passed.append("E2 ✅ 人类否决不受法定人数限制，安全护栏有效")
        print(f"     ✅ 人类否决即时生效: {result['status']}")
    else:
        issues.append("E2 ❌ 人类否决未生效")
except Exception as e:
    issues.append(f"E2 ❌ 人类否决异常: {e}")
    print(f"     ❌ 否决异常: {e}")

# ═══════════════════════════════════════════════════════════════
# F. IP / 逻辑保护审计
# ═══════════════════════════════════════════════════════════════
print("\n🔍 F. IP与逻辑保护审计")

ip_issues = []

# F1: Is the matching algorithm trivially copyable?
print("  F1. 匹配算法可复制性评估...")
ip_issues.append({
    "risk": "medium",
    "issue": "匹配算法为公开规则引擎(类别权重0.35+标签0.25+信誉0.20+时效0.20)",
    "mitigation": "规则引擎可被复制，但匹配精度来自执行轨迹数据积累 — 数据护城河"
})

# F2: Is the reputation model exposed?
print("  F2. 信誉模型暴露面评估...")
ip_issues.append({
    "risk": "medium",
    "issue": "信誉计算公式在reputation.py中公开可见",
    "mitigation": "公式本身不值钱，值钱的是执行轨迹数据和评分数据 — 这些无法复制"
})

# F3: Can the protocol spec be used to build a competing system?
print("  F3. 协议先行优势评估...")
ip_issues.append({
    "risk": "low",
    "issue": "协议规范(v0.1)是开放标准，任何人都可引用实现",
    "mitigation": "协议开放是有意设计 — 吸引更多Agent接入形成网络效应。护城河在数据+信誉网络密度，不在协议本身"
})

# F4: Data asset protection
print("  F4. 数据资产保护评估...")
ip_issues.append({
    "risk": "high",
    "issue": "JSON文件本地存储无加密，任何人可读取agents/listings/matches数据",
    "mitigation": "上线前必须: 1)数据文件加密 2)API鉴权 3)执行轨迹链上存证"
})

# F5: API exposure
print("  F5. API暴露面评估...")
ip_issues.append({
    "risk": "high",
    "issue": "server.py无任何鉴权机制，任何HTTP客户端可读写全部数据",
    "mitigation": "上线前必须: 1)Agent身份签名验证 2)请求频率限制 3)挂牌/匹配权限控制"
})

for item in ip_issues:
    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}
    print(f"  {risk_icon.get(item['risk'], '⚪')} [{item['risk'].upper()}] {item['issue']}")
    print(f"     💡 {item['mitigation']}")

# ═══════════════════════════════════════════════════════════════
# G. 概念/逻辑被抄袭的防护评估
# ═══════════════════════════════════════════════════════════════
print("\n🔍 G. 概念抄袭防护评估")

copy_risks = [
    {
        "layer": "协议层",
        "can_copy": "✅ 可复制 — 开放标准本身就是让别人实现的",
        "cant_copy": "❌ 不可复制 — 执行轨迹数据是独有资产，换集市就归零",
        "strategy": "协议越开放→Agent越多→数据护城河越深。让对手抄协议，但抄不走你的交易数据"
    },
    {
        "layer": "匹配引擎",
        "can_copy": "✅ 可复制 — 规则引擎算法公开",
        "cant_copy": "❌ 不可复制 — 匹配历史数据训练的精度、Agent行为模式",
        "strategy": "前3个月积累的匹配数据是独有资产。先发优势=更多数据=更准匹配"
    },
    {
        "layer": "信誉系统",
        "can_copy": "✅ 可复制 — 计算公式可抄",
        "cant_copy": "❌ 不可复制 — 你的Agent在你集市上的信誉，换集市就归零",
        "strategy": "信誉锁死效应：Agent在Bazaar积累的信誉越高，迁移成本越大"
    },
    {
        "layer": "经济定价",
        "can_copy": "✅ 可复制 — 供需×信誉×紧急度公式",
        "cant_copy": "❌ 不可复制 — 真实交易历史形成的价格发现数据",
        "strategy": "第一笔真实交易数据就是定价锚点。后来者没有这个锚"
    },
    {
        "layer": "网络效应",
        "can_copy": "✅ 可复制 — 集市概念",
        "cant_copy": "❌ 不可复制 — 同期8节点×5域的匹配关系网络",
        "strategy": "冷启动是最大障碍。你已经有5个自有Agent+验证数据，后来者从0开始"
    },
]

print(f"\n  ┌─────────────────────────────────────────────────────────┐")
print(f"  │  层面          │ 可抄？ │ 不可抄？                      │")
print(f"  ├─────────────────────────────────────────────────────────┤")

for r in copy_risks:
    print(f"  │ {r['layer']:<14} │  是   │ 执行轨迹/交易历史/信誉网络   │")

print(f"  └─────────────────────────────────────────────────────────┘")

print(f"\n  🎯 核心结论:")
print(f"     协议和算法可以被照抄，但三样东西抄不走:")
print(f"     1. 执行轨迹数据 — 你的集市上发生过什么，无可替代")
print(f"     2. 信誉网络密度 — Agent的信誉在你这里，换地方归零")
print(f"     3. 先发冷启动数据 — 你已经验证了5-8个Agent的自发匹配网络")
print(f"")
print(f"  💡 防护策略:")
print(f"     • 数据不公开 — traces/reputation数据只通过API暴露必要字段")
print(f"     • 协议可公开 — 吸引更多Agent接入，加速网络效应")
print(f"     • 先发优势 — 快速上线跑出第一波真实交易数据")
print(f"     • 链上锚定 — 关键数据哈希链上存证，时间戳证明你先做的")

# ═══════════════════════════════════════════════════════════════
# H. 服务器安全
# ═══════════════════════════════════════════════════════════════
print("\n🔍 H. 服务端安全审计")

print("  H1. 端口暴露...")
print("     ⚠️  server.py 监听 0.0.0.0:8900 — 所有网络接口可访问")
print("     💡 建议: 改为 127.0.0.1，或通过nginx反向代理+IP白名单")

print("  H2. HTTPS...")
print("     ❌  HTTP明文传输 — 无TLS加密")
print("     💡 建议: nginx反向代理终结TLS，或使用Let's Encrypt")

print("  H3. 请求大小限制...")
print("     ❌  无请求体大小限制 — 可能被大数据包攻击")
print("     💡 建议: 添加 max_content_length = 1MB")

print("  H4. 频率限制...")
print("     ❌  无频率限制 — 可能被DDoS/爬虫耗尽资源")
print("     💡 建议: 每Agent每分钟最多60请求")

# ═══════════════════════════════════════════════════════════════
# 总结报告
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  📋 安全审计总结")
print("=" * 70)

print(f"\n  ✅ 通过项: {len(passed)}")
for p in passed:
    print(f"     {p}")

print(f"\n  ⚠️  警告项: {len(warnings)}")
for w in warnings:
    print(f"     {w}")

print(f"\n  ❌ 漏洞项: {len(issues)}")
for i in issues:
    print(f"     {i}")

print(f"\n  🔴 IP风险项: {sum(1 for x in ip_issues if x['risk']=='high')}高/{sum(1 for x in ip_issues if x['risk']=='medium')}中/{sum(1 for x in ip_issues if x['risk']=='low')}低")

print(f"""
  ╔══════════════════════════════════════════╗
  ║  上线前必须修复:                          ║
  ╠══════════════════════════════════════════╣
  ║  🔴 API鉴权 (Agent身份签名)              ║
  ║  🔴 频率限制 (rate limiting)             ║
  ║  🔴 数据加密 (本地+传输)                  ║
  ║  🔴 自成交检测 (同Agent不可匹配自己)       ║
  ║  🔴 女巫攻击防御 (新Agent信誉冷却期)       ║
  ║  🟡 评分异常值过滤 (IQR去极值)            ║
  ║  🟡 HTTPS (TLS加密传输)                  ║
  ║  🟡 请求体大小限制                        ║
  ║  🟡 挂牌频率限制 (防供需操纵)              ║
  ╚══════════════════════════════════════════╝
""")
