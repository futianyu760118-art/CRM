# Sales Agent / Skill Registry V1.0

> 日期：2026-10-10  
> 适用：AEOS M05 销售自治中心 + M10 销售岗位 Personal Agent  
> 状态：PROPOSED / MVP Scope 已标记

## 1. Personal Agent

### sales.personal
- 类型：Personal Agent
- Runtime Owner：M01
- Assembly/UI Owner：M10
- Business Context：M05
- 面向：销售人员
- 职责：统一接收用户意图、读取个人待办/异常/结果，编排已批准 Sales Domain Agent。
- 禁止：直接修改价格、批准报价、承诺交期、自动发送外部邮件。

## 2. MVP Domain Agents

### sales.inquiry
- Owner：M05
- MVP：是
- 职责：解析询盘、结构化抽取、A/B/C 分类、识别缺失信息。
- Skills：
  - inquiry_extract@1
  - inquiry_classify@1
  - customer_match@1
  - product_match@1
  - evidence_link@1
- 禁止：自动对外发送。

### sales.quotation
- Owner：M05
- MVP：是
- 职责：准备报价候选、判断授权层级、生成报价草稿、提交 Guard/Approval。
- Skills：
  - quote_context_load@1
  - quote_range_get@1
  - discount_level_check@1
  - delivery_result_get@1
  - certification_result_get@1
  - quote_draft_generate@1
  - quote_guard_check@1
- 禁止：读取成本/底价；无 Guard 批准不得正式发布。

### sales.followup
- Owner：M05
- MVP：是
- 职责：按 SLA、客户状态、报价状态生成跟进建议和 Action。
- Skills：
  - followup_due_check@1
  - communication_context_load@1
  - followup_draft@1
  - overdue_escalate@1
- 禁止：自动发送外部消息。

### sales.opportunity
- Owner：M05
- MVP：是
- 职责：商机阶段评估、停滞识别、风险提示、下一步建议。
- Skills：
  - opportunity_health@1
  - stage_transition_check@1
  - stale_opportunity_detect@1
  - next_action_recommend@1

## 3. Phase-2 Domain Agents

### sales.customer_research
- 公开信息背调、画像、置信度和 Evidence。
- 不得把推断写成事实。

### sales.product_match
- 客户叫法 → Sales Product View。
- 正式产品事实来自 M04 Facade。

### sales.compliance
- 价格、交期、认证、独家、账期、敏感表述检查。
- 规则优先，模型辅助。

### sales.customer_operation
- 客户经营、复购、沉默、重点客户维护。

### sales.sales_risk
- 超期、失联、报价即将过期、交付/信用风险聚合。

### sales.commercial_order
- 商务订单候选、M06 Delivery Promise、M09 Credit Result 联动。

### sales.review
- 赢单/失单复盘、改进候选、知识回流。

## 4. Acquisition Agent

### sales.lead_acquisition
- Owner：M05
- 编排工具：允许 Dify
- 内部 Workflow：
  - search_orchestration
  - website_parse
  - contact_discovery
  - profile_enrichment
  - candidate_lead_prepare

输出必须是 Candidate Lead，不直接写正式 Lead。

首批 Skills：
- public_search@1
- website_parse@1
- contact_extract@1
- email_verify@1
- lead_deduplicate@1
- lead_score@1
- candidate_evidence_build@1

## 5. Skill 分层

### 专业 Skill
由 M05 维护：
- inquiry_extract
- inquiry_classify
- opportunity_health
- quote_guard_check
- followup_due_check

### 跨域 Skill
只通过 Contract 调用：
- product_release_get → M04
- delivery_promise_get → M06
- quality_release_get → M08
- credit_result_get → M09
- evidence_submit → M02

### Tool
- CRM API
- M02 API
- M04 API
- M06 API
- M08 API
- M09 API
- Event Bus
- File/Evidence Upload

## 6. MVP 装配模板

### 普通业务员

```
sales.personal
├─ sales.inquiry
├─ sales.quotation
├─ sales.followup
└─ sales.opportunity
```

### 销售主管

```
sales.personal
├─ sales.opportunity
├─ sales.quotation
├─ sales.sales_risk
├─ team_exception_view
└─ approval_action
```

### 销售总监

```
sales.personal
├─ sales.sales_risk
├─ sales.review
├─ sales.customer_operation
├─ pipeline_result_view
└─ exception_decision
```

## 7. Guard Registry（首批）

- G-SALES-001：AI_CANNOT_SEND_EXTERNAL_MESSAGE
- G-SALES-002：AI_CANNOT_ACCESS_COST_OR_BOTTOM_PRICE
- G-SALES-003：DELIVERY_PROMISE_REQUIRES_M06_RESULT
- G-SALES-004：CERTIFICATION_CLAIM_REQUIRES_EVIDENCE
- G-SALES-005：DISCOUNT_EXCEPTION_REQUIRES_APPROVAL
- G-SALES-006：CREDIT_TERM_REQUIRES_M09_RESULT
- G-SALES-007：EXCLUSIVE_RIGHTS_REQUIRE_EXECUTIVE_APPROVAL
- G-SALES-008：CANDIDATE_LEAD_REQUIRES_VALIDATION_BEFORE_FORMALIZATION

## 8. MVP 验收

必须完成：
- Personal Agent 只呈现一个入口；
- 后台至少 4 个 Domain Agent 可编排；
- 每个 Agent 有 Owner、Registry、版本；
- Agent 只调用批准 Skill；
- 所有正式写入携带 correlation_id / trace_id；
- 重大动作有 Guard；
- Agent 不可用时进入人工队列；
- 至少一条 Inquiry→Quote→Follow-up→Result→Evidence 闭环通过。
