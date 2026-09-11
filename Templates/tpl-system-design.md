---
title: "{{title}} 高并发高可用系统设计实战"
created: {{date}}
updated: {{date}}
type: project
tags:
  - category/project
  - category/interview
  - topic/system-design
status: stable
audience: both
---

# {{title}} 高并发高可用系统设计实战

---

## 1. 需求分析与规模估算 (Requirements & Estimation)

- **功能性需求**：
- **非功能性需求**：高可用 (99.99%)、低延迟 (P99 < 50ms)、数据强一致
- **容量与 QPS 估算**：
  - 日活 DAU：`1000 万`
  - 峰值写 QPS：`50,000`；峰值读 QPS：`200,000`

---

## 2. 总体架构拓扑图 (High-Level Architecture)

```text
[Client] ──(CDN/DNS)──> [L4/L7 LB] ──> [API Gateway] ──> [Business Microservices]
                                                              │       │
                                                 ┌────────────┘       └────────────┐
                                                 ▼                                 ▼
                                      [Redis Cluster (Cache)]              [Kafka (Async MQ)]
                                                 │                                 │
                                                 ▼                                 ▼
                                      [MySQL Sharding (DB)]               [Async Worker Pool]
```

---

## 3. 核心数据模型与索引设计 (Data Model & Storage)

```sql
-- 核心表结构与索引设计
```

---

## 4. 极端场景容灾与高可用方案 (Fault Tolerance & Scalability)

- **降级与熔断**：
- **防刷与限流**：
- **数据最终一致性保障**：
