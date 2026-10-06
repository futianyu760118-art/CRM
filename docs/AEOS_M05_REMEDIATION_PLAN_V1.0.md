# AEOS M05 销售自治中心整改实施计划 V1.0

- 目标仓库：`futianyu760118-art/CRM`
- 上位标准：AEOS V7.2
- 依据：《CRM × AEOS V7.2 对标检查报告 V1.0》
- 原则：先边界、后功能；先闭环、后扩展；代码完成不等于业务完成。

## 1. 整改目标

将现有 CRM 从独立销售业务系统演进为 AEOS M05 销售自治中心，并满足：
1. 边界清晰。
2. Business Object 可识别。
3. Event 可发布 / 回放。
4. Decision / Action 可追踪。
5. Result 可验证。
6. Evidence 可穿透。
7. 与 M01 / M02 / M03 / M04 / M06 / M08 / M09 / M11 / M12 通过标准契约协同。
8. Agent 只在权限和 Guard 内运行。

## 2. 分阶段实施

### P0：架构冻结与安全基线（第 1-2 周）

交付物：
- M05_DOMAIN_BOUNDARY_V1.md
- M05_DATA_OWNERSHIP_V1.md
- M05_OBJECT_CATALOG_V1.md
- M05_CONTRACT_MAPPING_V1.md
- SECURITY_BASELINE_V1.md

代码任务：
- BaseModel / BusinessModel 增加：
  - tenant_id
  - source_system
  - revision
- API 增加：
  - X-Correlation-ID
  - X-Trace-ID
  - Idempotency-Key
- Production 配置禁止默认 Secret / Password。
- 对 User / Department 标记为 M01 Compatibility Model。

验收：
- 无新增跨域直接写表。
- 每个 M05 Object 有唯一 Owner。
- 所有写 API 有 actor + correlation_id。
- prod 环境默认口令启动失败。

### P1：统一 Event / Result / Evidence（第 3-4 周）

新增核心对象：
- AEOSObjectRef
- AEOSBusinessEvent
- AEOSResult
- AEOSEvidence

升级 IntegrationOutbox：
- event_id
- source_system
- object_ref
- occurred_at
- correlation_id
- causation_id
- actor_id
- payload_version
- evidence_refs
- idempotency_key

首批事件：
- LeadCreated
- LeadAssigned
- LeadConverted
- CustomerCreated
- OpportunityCreated
- OpportunityStageChanged
- InquiryCreated
- InquirySubmitted
- QuoteCreated
- QuoteSubmitted
- QuoteApproved
- QuoteRejected
- CommercialOrderRequested
- CommercialOrderConfirmed
- SalesActionCreated
- SalesResultSubmitted
- SalesResultVerified
- EvidenceSubmitted

验收：
- 同一 idempotency_key 重放不重复创建业务事实。
- 任一事件可回溯 object_ref 和 actor。
- Result 必须能关联 Evidence。

### P2：Decision / Action / Guard 闭环（第 5-6 周）

目标链路：
Fact → Event → DecisionCase → Decision → Action → Result → Verify → Evidence

改造：
- Task 映射 AEOS Action。
- Approval 映射 Guard / Decision。
- next_action 不再只是文本字段，正式行动必须有 action_id / owner / due_at / verification_rule。
- done 与 verified 分离。

首个闭环建议：
“重点商机跟进闭环”

触发：
- 高价值 Opportunity 7 天未跟进
- 报价超过 SLA
- 客户连续 30 天无互动
- 报价后 14 天无反馈

动作：
- 自动形成 DecisionCase。
- Agent 给出建议。
- 人类责任人确认。
- 生成 Action。
- 完成后提交 Result。
- Evidence 验证后关闭。

### P3：M02 / M03 / M11 接入（第 7-8 周）

M02：
- Object Sync
- Event Publish
- Evidence Submit
- Result Publish
- Audit / Provenance

M03 EBMS：
只输出：
- SalesResult
- SalesException
- SalesDecision
- EvidenceRef

禁止 EBMS 直接查询 CRM 内部复杂表进行业务拼装。

M11：
- Event Bus Adapter
- API Gateway Adapter
- Connector Registry

验收：
- CRM 数据库停掉只读副本时，EBMS 仍可通过 Result Contract 获取管理结果。
- Event 至少支持一次重放。
- M02 可穿透至 Evidence。

### P4：跨域闭环（第 9-10 周）

优先实现 3 条：

1. Inquiry → R&D
- M05 发布客户需求。
- M04 返回技术可行性 / Release Result。

2. Commercial Order → Delivery
- M05 发起交期承诺请求。
- M06 返回 Capacity / Material / Delivery Promise Result。
- 未通过 Guard 不允许正式承诺。

3. Sales → Finance
- M09 返回 Credit / AR / Margin / Cash Result。
- M05 消费，不复制维护第二套财务事实。

### P5：Agent / Skill 自治层（第 11-12 周）

第一批 Agent：
- Sales Manager Agent
- Sales Rep Agent
- Inquiry Triage Agent
- Quotation Agent
- Customer Operation Agent

第一批 Skills：
- opportunity_review
- customer_health_check
- inquiry_triage
- quotation_prepare
- followup_recommend
- sales_risk_detect
- evidence_collect
- result_verify_assist

约束：
- Agent 无权直接绕过 Guard 修改重大正式数据。
- Agent 所有建议保留 source / model / prompt_version / evidence_refs。
- 人类确认动作有明确 actor_id。

## 3. 优先级清单

### P0 必须做
- Domain Boundary
- Data Ownership
- Security Defaults
- Common Envelope
- Correlation / Trace
- Event Contract

### P1 必须做
- Result
- Evidence
- Action
- Decision / Guard Mapping
- M02 Adapter

### P2 应做
- EBMS Result Projection
- M06 Delivery Promise
- M04 Requirement Handoff
- M09 Credit / AR / Margin

### P3 后做
- Agent
- Skill
- Memory
- 自进化策略

## 4. 建议代码结构

```
backend/app/aeos/
  contracts/
    common.py
    object.py
    event.py
    result.py
    evidence.py
    decision.py
    action.py
  adapters/
    kernel.py
    data_foundation.py
    event_bus.py
    ebms.py
    rd.py
    delivery.py
    quality.py
    finance.py
  services/
    event_publisher.py
    result_service.py
    evidence_service.py
    decision_service.py
    action_service.py
    guard_service.py
  agents/
    sales_manager/
    sales_rep/
    inquiry_triage/
    quotation/
  skills/
    opportunity_review/
    customer_health_check/
    inquiry_triage/
    quotation_prepare/
    followup_recommend/
```

## 5. 数据迁移策略

不建议立即重构全部旧表。

采用 Strangler / Adapter 模式：
1. 原 CRM 表继续运行。
2. 新增 AEOS Contract Layer。
3. 旧模型通过 Adapter 映射为 Object / Event / Result。
4. 新功能只写标准契约。
5. 逐步减少旧字段承担跨域语义。
6. 最后再决定是否拆服务。

这样能避免系统过重，同时满足 AEOS 的“轻版先验证、重版再深化”。

## 6. 第一轮实际开发包

建议马上进入 Sprint M05-G0：

### Backend
- `app/aeos/contracts/common.py`
- `app/aeos/contracts/event.py`
- `app/aeos/contracts/result.py`
- `app/aeos/contracts/evidence.py`
- `app/aeos/services/event_publisher.py`
- `app/middleware/context.py`
- migration：补 tenant_id / revision / correlation_id

### Docs
- M05_DOMAIN_BOUNDARY_V1.md
- M05_DATA_OWNERSHIP_V1.md
- M05_EVENT_CATALOG_V1.md
- M05_G0_ACCEPTANCE_V1.md

### Tests
- Contract schema test
- Idempotency test
- Permission enforcement
- Event replay
- Evidence traceability
- Result verification
- Production config safety test

## 7. 12 周验收标准

最终不能只看“页面做完”。

必须至少演示 1 条完整链路：

客户询价
→ InquiryCreated
→ 技术 / 交付约束事件
→ Decision
→ 报价 Action
→ Quote Result
→ 人工审批 Guard
→ 客户确认
→ Commercial Order
→ Delivery Promise
→ Result Verified
→ Evidence
→ EBMS 展示结果

验收条件：
- 每个关键对象可追溯 Owner。
- 所有关键状态变化有 Event。
- 重大动作有 Decision / Guard。
- Action 有责任人和截止时间。
- Result 有验收标准。
- Evidence 可穿透。
- EBMS 不直连内部业务表。
- 跨域无直接写库。
- Contract Test 全部通过。

## 8. 建议立即执行顺序

1. 先冻结 M05 边界。
2. 再加 Common Envelope。
3. 升级 Outbox 为 Event Contract。
4. 增加 Result / Evidence。
5. 把 Task / Approval 映射到 Action / Guard。
6. 打通 M02。
7. 输出 EBMS Result。
8. 打通 M06 订单承诺。
9. 最后上 Agent / Skill。

这条路线能最大程度复用当前代码，同时避免把 CRM 推倒重写，也避免继续做成一个越来越重的独立系统。
