# AEOS 冻结契约 schema 快照

| 项 | 值 |
|---|---|
| 来源仓库 | `futianyu760118-art/EBMS` |
| 源文件 | `contracts/aeos-contracts-v1.schema.json` |
| 源提交 | `1d10853` |
| 复制日期 | 2026-11-03（PAND-330） |
| `$id` | `https://ebms.local/contracts/aeos-contracts-v1.schema.json` |
| `contract_version` | `AEOS.Contracts.V1` |

用途：CRM 侧离线漂移检查（F7-A01/F7-A05）的唯一权威基线。**不得就地修改**；
上游 schema 变更须回 PAND-248 走版本演进，并同步替换本快照与 `backend/app/contracts/drift.py`
的比对映射。
