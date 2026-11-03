# AEOS M05 销售自治中心 + M10 销售岗位微系统总体方案 V2.0

> 日期：2026-10-10  
> 上位框架：AEOS V7.2  
> 目标仓库：CRM  
> 状态：PROPOSED / G0 待审批  
> 依赖标准：
> - AEOS_AGENT_GOVERNANCE_V1
> - M05_M10_BOUNDARY_STANDARD_V1
> - SALES_AGENT_SKILL_REGISTRY_V1
> - AEOS POMS V2.2
> - AEOS Contract Pack / DEH Contract

## 1. 版本变化

V2.0 相比原 CRM + AI 方案做四项结构升级：

1. 不再把 AI 定义为“询盘智能体 + 获客智能体”两个附加功能，而是纳入 AEOS Agent Framework。
2. M05 销售自治中心与 M10 个人微系统彻底分离。
3. 每个人拥有一个 Personal Agent 逻辑实例，由多个批准的 Domain Agent / Skill 支撑。
4. 工作台归 M10，管理经营结果归 M03，CRM 保留销售专业后台。

## 2. 总体架构

```
                     AEOS V7.2
                         │
        ┌────────────────┼────────────────┐
        │                │                │
      M01              M02              M03
 Agent/Skill/Guard   Object/Event      EBMS
 Identity/Goal      Result/Evidence    Management
        │                │                │
        └────────┬───────┴────────┬───────┘
                 │                │
        ┌────────▼────────┐       │
        │ M05 Sales       │───────┘
        │ Autonomy Center │
        │                 │
        │ Lead            │
        │ Customer        │
        │ Opportunity     │
        │ Inquiry         │
        │ Quote           │
        │ CommercialOrder │
        │ Customer Ops    │
        │ Domain Agents   │
        └────────┬────────┘
                 │ Contract / Event / Result
        ┌────────▼────────┐
        │ M10 POMS        │
        │ Personal Agent  │
        │ Todo            │
        │ Exception       │
        │ Result          │
        │ Mobile Input    │
        └─────────────────┘
```

## 3. M05 定位

M05 是销售专业事实和专业规则 Owner。

主链路：

```
Lead
→ Customer
→ Opportunity
→ Inquiry
→ Quotation
→ Commercial Order
→ Customer Operation
```

M05 输出给 AEOS：
- SalesResult
- SalesException
- SalesDecisionRef
- SalesEvidenceRef
- SalesEvent

## 4. M10 定位

M10 不再承担第二套 CRM。

每个人只有一个 Personal Agent 入口，首页只保留：
- 未来待办
- 当前异常
- 过去结果
- AI 对话
- 快捷输入

Personal Agent 根据 actor_id / role_context / goal / permission / business_context 动态装配。

## 5. Sales Personal Agent

### 5.1 普通业务员 MVP

```
Sales Personal Agent
├─ Inquiry Agent
├─ Quotation Agent
├─ Follow-up Agent
└─ Opportunity Agent
```

第一阶段不一次性开发十几个 Agent。

### 5.2 销售主管

在普通业务能力基础上增加：
- Sales Risk
- Team Exception
- Approval
- Pipeline Review

### 5.3 销售总监

面向 Result / Exception / Decision，不以邮件和明细操作为主：
- Pipeline Result
- Key Account Risk
- Pricing Exception
- Sales Review
- Goal Gap

## 6. 原有 15 项 AI 功能重新归属

| 原功能 | V2.0 归属 |
|---|---|
| 邮件自动进入与抽取 | M05 Inquiry Agent |
| A/B/C 分级 | Inquiry Skill |
| 客户背调 | Customer Research Agent |
| 产品匹配 | Product Match Skill + M04 Facade |
| 回复草稿 | Communication Skill |
| 草稿审核 | Sales Compliance / Guard |
| 报价授权 | Quotation Agent + Guard |
| 价格红线 | M01 Guard + M05 Pricing |
| 销售产品库 | M04 Sales Product Facade |
| 主动获客 | Lead Acquisition Agent |
| 邮箱验证去重 | Acquisition Skills |
| 破冰草稿 | Communication Skill |
| 销售工作台 | M10 POMS |
| 经营看板 | M03 EBMS |
| 客户交接 | M05 Business Memory + M10 Handover |

## 7. 询盘闭环

```
Email / Platform Message
→ Candidate Inquiry
→ Inquiry Agent
→ Customer Match
→ Product Match
→ A/B/C Classification
→ Evidence Link
→ Personal Todo
→ Human Review
→ Quote Preparation
→ Guard
→ Human Confirm
→ Send
→ Follow-up Action
→ Result
→ Verify
→ Evidence
```

对外发送永远由授权人确认。

## 8. 获客闭环

```
Public Source
→ Lead Acquisition Agent
→ Candidate Lead
→ Public Evidence
→ Validation
→ Dedup
→ Human/System Review
→ M05 Lead API
→ LeadCreated
→ Assigned Action
```

Dify C0~C4 保留为内部 Workflow/Skill，不作为五个顶层 Agent。

## 9. Product 处理

当前 CRM Product / SKU 不作为最终 Product Master。

迁移目标：
- M04 保留正式 Product / SKU / Spec / Certification / Release。
- M05 保留 Sales Product View。
- 旧 Product 表通过 Adapter 过渡。
- 新跨域功能禁止继续增强 CRM 成为第二产品主数据中心。

## 10. 价格与审批

### 10.1 AI 红线
AI 永远不能读取：
- 成本
- 公司底价
- 历史最低成交底价

AI 可读取：
- 允许报价区间
- 报价条件
- 授权状态
- Guard 结果

### 10.2 人员价格可见性
当前销售资料存在冲突。V2.0 将可见性改为 Policy，不写死在业务代码。

推荐默认：
- 普通业务员：可报价区间；
- 核价角色：内部价格；
- 主管/总经理：按授权查看。

### 10.3 审批超时
废除“默认超时即批准”作为平台默认规则。

改为：
- reminder
- delegate
- escalate
- exception

## 11. Memory

```
Enterprise Memory
Role Memory
Business Memory
Personal Memory
```

Customer / Quote / Order / Commitment 属于 Business Memory。

个人离职：
- Business Memory 保留；
- Personal Memory 按 Policy 封存/清理；
- 未完成 Action 经 Handover 转移。

## 12. Guard

首批强制 Guard：
- AI 禁止直接对外发送
- AI 禁止读取底价/成本
- 交期承诺必须有 M06 Result
- 认证声明必须有 Evidence
- 超授权让利必须审批
- 账期必须有 M09 Result
- 独家/区域保护必须高级审批
- Candidate Lead 正式化必须验证

## 13. MVP 范围

### 必须
- Personal Agent 统一入口
- Inquiry Agent
- Quotation Agent
- Follow-up Agent
- Opportunity Agent
- 8~12 个 Skills
- Todo / Exception / Result
- Guard
- Result / Evidence
- Agent Audit
- Fallback Human Queue

### 暂缓
- 大规模主动获客自动化
- 十几个 Agent 全量上线
- 自动自进化
- 复杂预测模型
- 多模型自主选择
- 自动外发
- 自动审批重大业务

## 14. 第一阶段验收场景

唯一主验收链：

```
A 类新询盘
→ 10 分钟内结构化完成
→ 进入业务员 Personal Agent 待办
→ 产品匹配
→ 报价候选
→ Guard
→ 人工确认
→ 对外发送
→ D+1/D+3/D+7 跟进
→ Result
→ Evidence
```

验收不是“页面完成”，而是整条链闭环。

## 15. KPI

### 过程
- A 类漏检率目标 0
- A 类人工发出 <=2h
- 24h 首响率 >=95%
- 有效跟进率 >=80%
- 失单原因回填率 100%

### Agent
- Inquiry structured accuracy
- Product match accuracy
- Quote guard violation = 0
- Hallucination critical error = 0
- Manual override rate
- Adoption rate
- P95 latency
- Cost per completed business case

禁止把“AI 调用次数”作为员工绩效。

## 16. 开发顺序

### Sprint 0：冻结
- Agent Governance
- M05/M10 Boundary
- Agent/Skill Registry
- Price Visibility Decision
- Approval Timeout Decision

### Sprint 1：M05 Contract Layer
- Common Envelope
- Event
- Result
- Evidence
- Correlation / Trace

### Sprint 2：POMS Sales Template
- Personal Agent Assembly
- Todo / Exception / Result UI
- Sales Rep Role Template

### Sprint 3：MVP Agents
- Inquiry
- Quotation
- Follow-up
- Opportunity

### Sprint 4：Cross-domain
- M04 Product Facade
- M06 Delivery Promise
- M09 Credit/AR
- M02 Evidence

### Sprint 5：Evaluation
- M12 Agent Evaluation
- Red-team
- UAT
- Canary
- Rollback

## 17. 受控决策项

以下必须由 Business Owner 签批：
1. 普通业务员是否可见底价。
2. L2 超时处理最终制度。
3. L1/L2/L3 的正式折扣阈值。
4. A/B/C 分类正式规则。
5. Opportunity 阶段。
6. 产品 Sales View 的正式字段。
7. 各 Agent 的业务 Owner。

未签批前，不允许开发团队自行固化为生产规则。

## 18. 版本结论

V2.0 的目标不是“CRM 加很多 AI”，而是：

**M05 提供销售专业事实和 Domain Agent；M10 给每个人装配 Personal Agent；M01 统一治理 Agent/Skill/Memory/Guard；M02 保存统一 Event/Result/Evidence；M03 消费经营结果。**

该结构可直接复制到研发、交付、品质、财经等自治中心。
