# CRM × AEOS V7.2 对标检查报告 V1.0

- 仓库：`futianyu760118-art/CRM`
- 对标基线：`futianyu760118-art/AEOS-` main
- 检查日期：2026-10-06
- 目标定位：AEOS M05 销售自治中心
- 当前 CRM 基线提交：`f588655f5c9349a6e9ac18c3cb0b48278ed6994e`

## 1. 总体结论

当前 CRM 已具备较完整的传统销售 CRM / 询报价业务骨架，包含线索、客户、联系人、商机、询价、报价、审批、任务、审计、权限范围、K3 集成与 Outbox 等能力，具备继续演进的工程基础。

但从 AEOS V7.2 的标准看，它目前仍是“独立业务系统”，尚未成为真正的 M05 销售自治中心。主要缺口集中在：

1. 未实现 AEOS 统一 Object / Event / Result / Evidence / Decision / Action 契约。
2. 未接入 M01 Kernel 的统一身份、目标、权限、Guard、Agent / Skill / Memory。
3. 未接入 M02 Enterprise Data & Evidence Platform 作为统一事实与证据底座。
4. 销售流程仍以 CRUD + 状态流转为主，尚未形成 Fact → Event → Decision → Action → Result → Verify → Evidence 的自治闭环。
5. 缺少标准 Result 输出给 M03 EBMS 的机制。
6. 缺少跨域契约化协同：M04 研发、M06 交付、M08 品质、M09 财经目前没有统一 Contract Gate。
7. 缺少岗位 Agent / Skill 和“目标驱动行动”机制。
8. 当前安全配置仍存在开发默认密钥与默认数据库口令，不满足正式 Gate。

综合判断：**当前匹配度约 52/100，达到“业务系统可运行”，未达到“AEOS 销售自治中心可验收”标准。**

## 2. 已符合 / 可复用能力

### 2.1 销售主链路基础较完整

现有数据模型已经覆盖：
- Lead
- Company / Contact
- Opportunity
- Inquiry
- Product / SKU
- Pricing / Quotation
- Task / Activity
- Approval

这些能力可以继续保留，不建议推倒重写。

### 2.2 已有基础权限与数据范围能力

`backend/app/services/data_scope.py` 已实现 SELF / DEPT / DEPT_AND_CHILD / CUSTOM / ALL 等范围控制，可作为 M01 权限接入前的过渡实现。

### 2.3 已有审批与人工责任链

`backend/app/services/approval.py` 已具备按角色、金额阈值的审批链，说明当前系统已经有“重大动作不能完全自动化”的工程基础。

但 AEOS 下应进一步演进为 Guard + Decision / Action Contract，而不是只保留单据审批。

### 2.4 已有审计能力

`backend/app/middleware/audit.py` 对写操作自动记录审计日志，`backend/app/models/audit.py` 保存用户、路径、资源、请求、结果和 request_id。

这与 AEOS 对“可追溯”的要求方向一致，可保留并升级为统一 Audit / Provenance。

### 2.5 已有 Outbox / 幂等雏形

`backend/app/models/integration.py` 已存在：
- IntegrationLog
- IntegrationOutbox
- idempotency_key
- retry_count
- staging tables

这是接入 M11 Event Bus / Connector 的重要基础，属于当前代码中与 AEOS 最接近的一块。

## 3. 主要不符合项

### G0-01：M05 边界未冻结【严重】

AEOS 定义：
- M05 拥有 Customer / Lead / Inquiry / Quote / 商务 Order。
- Product / BOM / Release 属于 M04。
- Delivery Execution 属于 M06。
- Revenue / Margin / AR / AP 属于 M09。
- Event / Evidence / Result / Audit 统一事实底座属于 M02。

当前 CRM 内部同时存在产品、销售、集成、审批等多类能力，但没有显式 Domain Boundary、Data Ownership 和 System Registry 映射。

风险：
- 后续 CRM 容易继续膨胀成“小 ERP”。
- 与研发、交付、财经会产生重复主数据。
- 跨系统会通过表字段和接口临时耦合。

整改要求：
- 新增 M05 Domain Boundary。
- 将 Product 只保留销售引用视图或销售缓存，不成为产品主数据 Owner。
- Order 承诺进入 M06 能力校验。
- 财务结果只消费 M09 Result。

### G0-02：统一对象契约缺失【严重】

AEOS Object Contract 最低要求：
- tenant_id
- object_type
- object_id
- source_system
- revision

当前业务模型未统一携带上述 Envelope；搜索未发现 tenant_id / object_type / source_system / revision 的标准实现。

后果：
- 无法在 M02 建立稳定 Business Object。
- 无法可靠进行跨模块追踪、回放、同步和多租户扩展。

### G0-03：标准 Event Contract 缺失【严重】

当前 IntegrationOutbox 只有：
- event_type
- biz_type
- biz_id
- payload
- status / retry

AEOS 要求：
- event_id
- event_type
- occurred_at
- source_system
- object_ref
- correlation_id
- causation_id
- actor_id
- payload_version
- evidence_refs
- idempotency_key

当前 Outbox 可以复用，但字段不足，且尚未形成企业级事件契约。

### G0-04：Result / Evidence 缺失【严重】

AEOS 明确要求各专业中心以 Result 向 EBMS 输出，而不是让 EBMS 直接拼内部业务表。

当前 CRM 未发现标准：
- Result
- Evidence
- Result Verification
- evidence_refs
- source/version/checksum/provenance

这意味着系统现在能记录“做了什么”，但不能标准化证明“结果是否达成”。

### G0-05：Decision / Action 自治链未建立【严重】

当前有 Task、审批、next_action，但未统一为：
Fact → Event → DecisionCase → Decision → Action → Result → Verify → Evidence

现状偏向 CRUD + 人工推进，没有形成 AEOS 的闭环语义。

### G0-06：未接 M01 Kernel【严重】

当前 CRM 自己维护 User / Role / Department / DataScope。

AEOS 标准要求：
- Person / Organization / Position 由 M01 唯一拥有。
- M05 只能引用。

整改方向：
- 短期保留本地用户体系作 Compatibility Adapter。
- 中期切换统一 SSO / Identity / Permission Contract。
- 禁止 CRM 成为第二套组织主数据 Owner。

### G0-07：未接 M02 Data & Evidence Platform【严重】

现有审计和集成日志是本地表。

AEOS 标准要求 M02 承担：
- Business Object
- Event
- Evidence
- Audit
- Result
- Value Ledger
- Provenance

因此 CRM 需要设计 M05 → M02 标准输出，而不是继续把证据和结果关在 CRM 自己数据库里。

### G1-01：跨域协同缺少 Contract Gate【高】

至少应建立：
- M05 → M04：客户需求 / Inquiry / Requirement
- M04 → M05：可销售产品 / Release / 技术确认
- M05 → M06：订单承诺请求
- M06 → M05：交期 / 产能 / 交付风险
- M08 → M05：质量放行 / 客诉 / CAPA Result
- M09 → M05：应收 / 毛利 / 回款 / 信用结果

目前 K3 集成是点对点集成，不等于 AEOS Contract。

### G1-02：订单承诺 Guard 缺失【高】

AEOS 要求销售商务 Order 的承诺必须经过 Delivery 能力验证。

当前未发现统一：
- Capacity Check
- Material Check
- Delivery Promise Result
- Guard Decision

风险是销售系统可独立产生交期承诺，跨域责任不清。

### G1-03：岗位 Agent / Skill 缺失【高】

未发现 Agent / Skill / Memory 结构。

M05 至少需要：
- Sales Manager Agent
- Sales Rep Agent
- Quotation Agent
- Customer Operation Agent
- Inquiry Triage Agent
- Follow-up Agent
- Risk Detection Skill
- Quotation Preparation Skill
- Customer Health Skill
- Opportunity Review Skill

Agent 只能建议、编排、生成候选 Action；重大正式数据必须经过权限 / Guard / 人类责任链。

### G1-04：目标驱动机制缺失【高】

当前系统有流程状态，但未把企业目标 / 部门目标 / 岗位目标作为 Action 生成依据。

AEOS 下应该支持：
Goal → Gap → Decision → Action → Result

例如：
- 目标：重点客户复购率 70%
- Gap：客户 45 天未跟进
- Event：CustomerEngagementRiskDetected
- Decision：进入重点跟进
- Action：3 天内完成技术复盘和报价更新
- Result：客户确认下一轮采购计划
- Evidence：邮件 / 报价 / 会议记录

### G1-05：EBMS 标准输出缺失【高】

M03 EBMS 应消费标准 Result / Exception / Decision / Evidence。

当前 Dashboard 直接面向 CRM 内部数据，后续容易把 EBMS 和 CRM 强耦合。

需要新增：
- SalesResult
- SalesException
- SalesDecision
- SalesEvidenceView

### G2-01：审计不足以替代 Evidence【中】

AuditLog 是“系统操作记录”，Evidence 是“业务结果证明”，二者不能混用。

需新增 Evidence 服务，并可关联：
- Quote
- Customer
- Opportunity
- Order
- Action
- Result
- Decision

### G2-02：缺少 correlation_id / trace_id【中】

Audit 当前有 request_id，但缺少跨服务 correlation_id / trace_id。

跨系统事件、决策、任务、结果无法形成统一链路。

### G2-03：安全配置不满足正式环境要求【严重】

`backend/app/core/config.py` 当前存在开发默认值：
- SECRET_KEY = dev-secret-key-please-change-in-production
- POSTGRES_PASSWORD = crm123456
- MINIO_ACCESS_KEY / MINIO_SECRET_KEY = minioadmin

开发环境允许存在默认值，但正式 Gate 必须：
- 禁止默认凭据启动生产环境。
- SECRET_KEY / DB / MinIO 凭据必须由 Secret Manager / 环境注入。
- CI 增加 Secret Scan / Config Gate。

## 4. 对标评分

| 维度 | 权重 | 当前得分 | 判断 |
|---|---:|---:|---|
| M05 业务主链路 | 20 | 16 | 较好 |
| 模块边界 / Data Ownership | 10 | 5 | 需冻结 |
| Object Contract | 8 | 2 | 缺失 |
| API Contract | 8 | 5 | 有 v1 和权限基础 |
| Event Contract | 10 | 4 | 有 Outbox 雏形 |
| Result Contract | 8 | 1 | 基本缺失 |
| Evidence / Provenance | 8 | 2 | 有 Audit，非 Evidence |
| Decision / Action 闭环 | 8 | 3 | 有 Task / Approval 雏形 |
| M01 Kernel 接入 | 5 | 1 | 当前本地实现 |
| M02 Data Foundation 接入 | 5 | 1 | 尚未接入 |
| Agent / Skill | 5 | 0 | 未发现 |
| DevSecOps / Gate | 5 | 2 | 基础不足 |
| **合计** | **100** | **42** | **未达到 AEOS G2** |

说明：从“独立 CRM 工程成熟度”看可高于 60，但按“AEOS M05 自治中心”标准评估为 42/100。此前初步估算 52/100，经代码级检查后下调为 42/100。

## 5. 建议目标架构

```
AEOS M01 Kernel
  ├─ Identity / Org / Role / Permission
  ├─ Goal
  ├─ Decision / Action / Guard
  └─ Agent / Skill / Memory
            │
            ▼
M05 Sales Autonomy Center
  ├─ Lead
  ├─ Customer / Contact
  ├─ Opportunity
  ├─ Inquiry
  ├─ Quote / Commercial Order
  ├─ Customer Operation
  ├─ Sales Agent Layer
  └─ M05 Contract Adapter
            │
     ┌──────┼───────────────┐
     ▼      ▼               ▼
M02 Data  M11 Event/API   M03 EBMS
& Evidence  Gateway       Result View
     │
     ├── M04 R&D
     ├── M06 Delivery
     ├── M08 Quality
     └── M09 Finance
```

## 6. 必须保留、必须改造、暂缓开发

### 保留
- Lead / Company / Contact / Opportunity / Inquiry / Quotation
- RBAC / DataScope 过渡实现
- Approval 基础能力
- Audit 中间件
- IntegrationLog / Outbox
- K3 Connector

### 改造
- BaseModel / BusinessModel 增加 AEOS Envelope
- Outbox 升级 Event Contract
- Task 升级 / 映射 Action Contract
- 审批映射 Guard / Decision
- 新增 Result / Evidence
- 新增 M02 / M11 Adapter
- 用户组织体系切为 M01 引用
- Dashboard 与 EBMS 解耦

### 暂缓
- 不扩张成为 ERP
- 不在 CRM 内自建完整财务
- 不在 CRM 内自建完整研发 BOM
- 不在 CRM 内自建交付排产
- 不允许 LLM 自动越权确认报价、订单、信用、重大承诺

## 7. Gate 结论

- G0 架构边界：**未通过**
- G1 单模块业务闭环：**部分通过**
- G2 平台契约：**未通过**
- G3 跨域闭环：**未通过**
- G4 自治 / Agent：**未通过**

当前建议状态：

**CRM = M05 Migration Candidate / Not AEOS-Ready**

完成 P0 / P1 整改后，可进入：

**M05 Sales Autonomy Center – G2 Candidate**

