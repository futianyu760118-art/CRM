# AEOS M05 销售自治中心 × M10 POMS 边界规范 V1.0

> 日期：2026-10-10  
> 上位框架：AEOS V7.2  
> 状态：PROPOSED / G0 待审批

## 1. 核心结论

M05 是“销售专业业务系统”；M10 是“个人工作入口/个人微操作系统”。

二者必须分离：
- M05 拥有销售专业事实、规则、状态和专业 Result。
- M10 不拥有销售专业主数据，只按人员、岗位、目标、权限和上下文装配个人工作界面与 Personal Agent。

## 2. M05 Owner 范围

M05 正式拥有：
- Lead
- Customer
- Contact
- Opportunity
- Inquiry
- Quotation
- Commercial Order（商务事实）
- Customer Interaction / Sales Activity
- Sales Result / Sales Exception

M05 不拥有：
- Person / Organization / Position：M01
- Product / BOM / Release / Certification Master：M04
- Delivery Execution / Capacity / Shipment：M06
- Quality Release / CAPA：M08
- Revenue / Margin / AR / AP / Credit：M09
- Event / Evidence / Audit / Provenance：M02

## 3. M10 Owner 范围

M10 只拥有轻量运行态：
- ui_manifest
- role_template_ref
- personal_context
- session_context
- notification_state
- local_pending_input
- sync_state

M10 不建立 Customer / Order / Quote / Product 等第二套业务表。

## 4. UI 边界

### M05
专业后台：
- 客户
- 商机
- 询盘
- 报价
- 商务订单
- 客户经营
- 专业配置
- 专业分析

### M10
个人唯一工作入口：
- Future Todo
- Current Exception
- Past Result
- Personal Agent
- 快捷扫码/拍照/语音/文本输入

### M03 EBMS
管理者主视图：
- Result
- Exception
- Decision
- Evidence

禁止 M05、M10、M03 同时建设同一套“个人工作台/经营总看板”。

## 5. Agent 边界

M01：
- Agent Runtime
- Agent Registry
- Skill Registry
- Memory Policy
- Permission / Guard

M05：
- Sales Domain Agents
- Sales Skills
- Sales Professional Result

M10：
- Personal Agent Assembly
- Role Template
- Personal Context
- UI / Interaction

## 6. Product 边界

CRM 当前 Product / SKU 逐步迁移为 Sales Product View。

M04 为正式 Product Owner。

M05 可维护销售增强字段：
- customer_alias
- sales_name
- selling_points
- recommended_market
- sales_faq
- public_quote_range
- sales_material_refs

M05 禁止成为：
- BOM Owner
- Formal Spec Owner
- Certification Master Owner
- Product Release Owner

## 7. 外部获客数据边界

标准流程：

```
Internet / Public Source
→ Lead Acquisition Agent
→ Candidate Lead
→ Evidence
→ Validation / Deduplication
→ M05 Lead API
→ LeadCreated Event
→ M02
```

外部采集信息默认是 Candidate Fact，不得直接成为正式主数据。

Dify 可作为编排工具，不得成为正式业务数据 Owner。

## 8. 价格与敏感信息

当前业务资料对“业务员是否可见底价”存在冲突，因此本规范不直接替业务 Owner 做最终制度决定。

系统必须支持 Policy 化：
- AI：禁止读取底价、成本价、历史成交底价。
- 普通业务员：建议默认只看允许报价区间。
- 核价/授权岗位：可按最小权限读取内部价格。

最终可见性由正式 Policy / Business Owner 签批决定，禁止硬编码。

## 9. 审批超时

L2 “超时默认同意”不得作为默认系统行为。

推荐标准：
- 超时提醒；
- 代理审批；
- 升级主管；
- 形成 Exception。

只有经正式 Policy 明确授权、低风险、可追溯的动作才允许自动通过。

## 10. 客户交接与 Memory

客户、邮件、报价、承诺、跟进记录属于 Business Memory，归 M05/M02。

人员调岗/离职：
- Personal Memory 封存或清理；
- Business Memory 保留；
- 未完成 Action 通过受控 Handover 转移；
- 临时代理权限有 expiry。

## 11. 核心交互 Contract

M10 向 M05 读取：
- My Leads
- My Customers
- My Opportunities
- My Inquiries
- My Quotes
- My Actions
- My Exceptions
- My Results

M10 写入 M05：
- Draft submission
- Action feedback
- Result submission
- Evidence reference
- User correction

所有写操作必须携带：
- tenant_id
- actor_id
- role_context
- object_ref
- correlation_id
- trace_id
- idempotency_key

## 12. 第一阶段 MVP

只验证一条闭环：

```
新询盘
→ 客户识别
→ 产品匹配
→ A/B/C 分级
→ 个人待办
→ Personal Agent 建议
→ 报价草稿
→ Guard
→ 人工确认
→ 跟进
→ Result
→ Evidence
```

MVP 不要求一次实现全部销售 Agent。

## 13. 验收红线

- M10 数据库中不存在销售主数据复制表。
- M05 不成为 Product/BOM/Finance/Delivery 主数据 Owner。
- M03 不直接拼 CRM 内部复杂表。
- Dify/Agent 不直接写正式事实表。
- Personal Agent 不拥有客户业务事实。
- 所有重大动作有 Owner + Guard + Evidence。
