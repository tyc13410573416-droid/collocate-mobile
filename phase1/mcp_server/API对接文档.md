# API 对接文档

> 赛题3「检验报告解读与用药禁忌核查」· 门控版
> 交付人：赖芷炫（Nexent 架构 + MCP + 门控规则引擎）
> 对接人：汤永超（前端三态可视化 + mock 联调）
> 版本：v1（2026-11-18）｜ 状态：**API 文档冻结前草稿**（11.22 冻结）

---

## 1. 文档目的

本文档约定赖芷炫负责的 **MCP 工具服务**与汤永超负责的**前端**之间的数据契约。前端 mock 联调、真实联调均以此为准。

**核心约定：门控 6 字段（11.17 已冻结，字段变更需三人同意）**

```
decision_gate    门控结论    "pass" | "review" | "abstain"
confidence       置信度      0~1 浮点
evidence_status  证据状态    "found" | "conflict" | "missing" | "low_confidence"
conflicts        冲突列表    数组，每项含 field / dimension / source_a / source_b / detail
next_action      下一步动作  给结论 / 人工复核 / 追问某字段（人话，前端可直接展示）
source_versions  来源版本    数组，每项含 source_id / version / effective_date
```

---

## 2. 服务接入信息

| 项目 | 值 |
|---|---|
| 传输协议 | MCP streamable-http |
| 服务地址 | `http://host.docker.internal:3001/mcp` |
| 服务名称 | `medical-report-agent` |
| 认证 | 无（内网直连，Bearer Token / Headers 留空） |

**注意**：URL 是 `host.docker.internal`，不是 `localhost`——Nexent 后端跑在 Docker 容器里，容器内的 `localhost` 指向容器自己，`host.docker.internal` 才是宿主机（MCP server 所在）。

**启动方式**（服务端，赖芷炫侧）：

```bash
C:/Python314/python.exe D:/ict1.0/nexent-mcp/server.py --http
```

启动后端口 `3001`，窗口保持打开（关闭即断连）。

---

## 3. 门控三态约定（前端配色参考）

| decision_gate | 含义 | 前端卡片色 | 何时出现 |
|---|---|---|---|
| `pass` | 证据一致、置信足够，直接给结论 | **绿** | 置信度 ≥ 0.8 且无冲突 |
| `review` | 来源参考区间冲突，只给说明不给结论 | **橙** | 多来源区间不一致 |
| `abstain` | 证据缺失或置信不足，拒答/追问 | **灰** | 缺数值 / 缺性别 / 置信 < 0.8 |

**置信度阈值：0.8**。低于 0.8 一律 `abstain`（规则由后端判定，前端只负责展示，不参与判断）。

---

## 4. 工具 1：query_reference（查参考区间）

**用途**：按指标名查参考区间，返回「来源 / 版本 / 性别」结构化字段，支撑前端"可点击来源 / 引用溯源"。

**入参**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| indicator | string | 是 | 指标名，支持中文（「谷丙转氨酶」）或英文缩写（ALT / CREA / GLU） |

**返回字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| found | bool | 是否查到 |
| source_id | string | 来源标识（如 `WS/T 404.1-2012`） |
| source_version | string | 版本号（当前为占位 `v1`，待知识库 v2） |
| effective_date | string | 生效日期（当前为年份占位，待 v2） |
| gender_range | object | 分性别参考区间，`male` / `female`，各含 `low` / `high` |
| reference_range | string | 原始区间文本 |
| unit | string | 单位 |
| abnormal_direction | string | 异常方向（偏高 / 偏低） |
| clinical_significance | string | 临床意义说明 |

**真实返回示例**（`query_reference("ALT")`）：

```json
{
  "found": true,
  "name": "丙氨酸氨基转移酶",
  "name_en": "ALT",
  "unit": "U/L",
  "reference_range": "男 9–50；女 7–40",
  "abnormal_direction": "偏高",
  "source_id": "WS/T 404.1-2012",
  "source_version": "v1",
  "effective_date": "2012",
  "gender_range": {
    "male": { "low": 9.0, "high": 50.0 },
    "female": { "low": 7.0, "high": 40.0 }
  }
}
```

未查到时的返回：

```json
{ "found": false, "message": "未找到指标「xxx」。", "source": null }
```

---

## 5. 工具 2：parse_report（检验单解析）

**用途**：把一段检验单文本解析成「指标名 + 数值 + 单位 + 置信度」，是前端"左检验单、右解答"的输入解析入口。

**入参**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| text | string | 是 | 检验单文本，如「谷丙转氨酶 68 U/L，肌酐 88 μmol/L」 |

**返回字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| matched_count | int | 识别到的指标数 |
| items | array | 每项含 `indicator`(缩写) / `name`(中文) / `value`(数值) / `unit`(单位) / `confidence`(0.9 或 0.5) |
| raw_text | string | 原始输入（回显） |

**confidence 规则**：指标名找到且数值找到 = `0.9`；只有指标名没有数值 = `0.5`。

**真实返回示例**：

```json
{
  "matched_count": 3,
  "items": [
    { "indicator": "ALT", "name": "丙氨酸氨基转移酶", "value": 68.0, "unit": "U/L", "confidence": 0.9 },
    { "indicator": "Cr", "name": "血肌酐", "value": 88.0, "unit": "μmol/L", "confidence": 0.9 },
    { "indicator": "K", "name": "血清钾", "value": 5.6, "unit": "mmol/L", "confidence": 0.9 }
  ],
  "raw_text": "谷丙转氨酶 68 U/L，肌酐 88 μmol/L，血钾 5.6 mmol/L"
}
```

---

## 6. 工具 3：evidence_gate（门控三态判定）★ 核心

**用途**：门控核心。输入指标 + 检测值 + 性别，输出冻结的 6 字段。**规则由后端确定性判定，前端只展示结果**。

**入参**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| indicator | string | 是 | 指标名（中文名或英文缩写） |
| value | float | 是 | 检测值 |
| gender | string | 否 | `male` / `female`，缺省为空 |
| age | string | 否 | 年龄（v1 暂不参与判定，预留） |

**返回字段（即冻结 6 字段）**：见第 1 节。`conflicts` 每项结构：

```json
{
  "field": "reference_range",
  "dimension": "male",
  "source_a": "WS/T 404.1-2012",
  "source_b": "WS/T 405-2020(模拟)",
  "detail": "WS/T 404.1-2012 男 9–50 vs WS/T 405-2020(模拟) 男 7–45"
}
```

`next_action` 是人话文案，前端可直接展示给用户（也可用 `decision_gate` 自己做样式）。

### 6.1 三态示例一：pass（通过）

输入 `evidence_gate("ALT", 200, gender="male")`：

```json
{
  "decision_gate": "pass",
  "confidence": 0.95,
  "evidence_status": "found",
  "conflicts": [],
  "next_action": "该检测值高于参考上限，方向为「偏高」中的偏高侧",
  "source_versions": [
    { "source_id": "WS/T 404.1-2012", "version": "v1", "effective_date": "2012" }
  ]
}
```

### 6.2 三态示例二：abstain（拒答/追问）

输入 `evidence_gate("ALT", 30)`（未传性别）：

```json
{
  "decision_gate": "abstain",
  "confidence": 0.7,
  "evidence_status": "low_confidence",
  "conflicts": [],
  "next_action": "该指标参考区间区分男女，请补充性别后重新解读",
  "source_versions": [
    { "source_id": "WS/T 404.1-2012", "version": "v1", "effective_date": "2012" }
  ]
}
```

> 说明：ALT 分男女区间，缺性别时置信度从 0.95 降到 0.70，低于阈值 0.8，触发 abstain。前端此时应弹「单字段追问输入框」（对应澄清分支）。

### 6.3 三态示例三：review（复核）—— 合成数据（演示用）

输入：ALT = 60，性别男，两个来源区间不一致（`WS/T 404.1-2012` 男 9–50 vs `WS/T 405-2020(模拟)` 男 7–45）：

```json
{
  "decision_gate": "review",
  "confidence": 0.95,
  "evidence_status": "conflict",
  "conflicts": [
    {
      "field": "reference_range",
      "dimension": "male",
      "source_a": "WS/T 404.1-2012",
      "source_b": "WS/T 405-2020(模拟)",
      "detail": "WS/T 404.1-2012 男 9–50 vs WS/T 405-2020(模拟) 男 7–45"
    }
  ],
  "next_action": "来源参考区间不一致，需人工复核后再给结论",
  "source_versions": [
    { "source_id": "WS/T 404.1-2012", "version": "v1", "effective_date": "2012" },
    { "source_id": "WS/T 405-2020(模拟)", "version": "v2", "effective_date": "2020" }
  ]
}
```

> ⚠️ 此条为**合成冲突案例**（两个来源数据是手工构造的，仅用于演示门控逻辑）。真实冲突数据待万嘉宜的「3+3 合成案例库」到位后替换。前端 mock 联调可先用这条结构占位。

---

## 7. 给前端的对接要点（汤永超）

1. **三个工具的关系**：`parse_report`（解析）→ `query_reference`（查区间）→ `evidence_gate`（判定）。前端可分别调用，也可由后端 Agent 编排串起来。
2. **三态配色**：pass 绿 / review 橙 / abstain 灰（见第 3 节）。
3. **conflicts 面板**：`review` 时渲染 `conflicts` 数组，展示「来源编号 + 冲突字段 + 差异详情」，并带「合成数据」横幅（合规要求）。
4. **可点击来源**：`source_versions[].source_id` 用于前端"可点击引用"。
5. **澄清追问**：`abstain` 且 `next_action` 含「补充性别」时，前端弹单字段输入框，用户补齐后重新调 `evidence_gate`。
6. **占位字段声明**：`source_version`（现为 `v1`）和 `effective_date`（现为年份）是占位值，等知识库 v2 到位后替换，**字段结构不变**，前端无需改。

---

## 8. 已知占位 / 待补（诚实声明）

| 项 | 现状 | 待补 |
|---|---|---|
| source_version / effective_date | 占位 `v1` + 年份 | 万嘉宜知识库 v2（含 version / effective_date / source_id） |
| 真实冲突案例 | 用合成数据验证了 review 逻辑 | 万嘉宜 3+3 合成案例库 |
| normalize / check_interaction | 未实现（阶段二 11.23–26 补） | 后续版本追加，字段结构会提前对齐 |

---

*本文档随 `server.py` 一起维护，工具字段变更时同步更新。*
