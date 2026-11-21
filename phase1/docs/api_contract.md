# Nexent API 接口约定

## 当前后端配置对齐

- RAG 配置：34 条
- 向量模型：`embedding-3`
- 大语言模型：`glm-4.7`
- 前端需要保留混合检索、重排、工具调用和引用信息，不能只返回一段纯文本。

## `parse_report` 字段规范（当前前端协议）

`parse_report` 负责把报告文本转换成结构化 JSON。字段名以 `test_name` 为准，`est_name` 视为笔误。

```json
{
  "patient_info": {"age": 45, "gender": "男"},
  "lab_results": [
    {
      "test_name": "丙氨酸氨基转移酶",
      "abbreviation": "ALT",
      "value": 68.0,
      "unit": "U/L",
      "reference_range": "9-50",
      "status": "high"
    }
  ],
  "medications": [{"drug_name": "阿托伐他汀钙片"}],
  "metadata": {"extraction_confidence": 0.95}
}
```

`parse_report` 同时返回 `patient_info.age` 和 `patient_info.gender`。Agent 必须把这两个字段继续传给 `query_reference` / `evidence_gate`，不能只把“男性/女性”当作普通文本丢弃。

约束：`value` 必须是纯浮点数；`status` 只能是 `high`、`low`、`normal`；年龄和性别要随后的知识库查询一起传入。当前网页在 `extraction_confidence < 0.8` 时显示红色“需人工核对”提示。为兼容阶段一旧页面，接口可以同时保留 `items` 字段。

## 证据决策门控字段

为避免多来源冲突时直接生成确定性结论，汇总节点还应返回：

```json
{
  "decision_gate": "pass",
  "confidence": 0.95,
  "evidence_status": "consistent",
  "conflicts": [],
  "next_action": "证据一致，可继续展示带来源结果",
  "source_versions": ["WS/T 405-v1（演示）"]
}
```

`decision_gate` 只能是 `pass`、`review` 或 `abstain`。来源版本冲突返回 `review`（只展示冲突，不给确定结论）；患者关键信息缺失、抽取置信度低于 0.8 或没有足够指标和参考范围时返回 `abstain`（拒答或追问）。前端会显示门控状态、冲突字段和下一步动作，不把门控结果包装成诊断结论。

## 阶段二工具协议

### `normalize`

请求：

```json
{
  "indicator": "HGB",
  "value": 11.8,
  "from_unit": "g/dL",
  "to_unit": "g/L"
}
```

返回：

```json
{
  "status": "pass",
  "indicator": "HGB",
  "value": 118.0,
  "unit": "g/L",
  "original_value": 11.8,
  "original_unit": "g/dL",
  "conversion": "g/dL → g/L",
  "factor": 10.0,
  "confidence": 0.99
}
```

无法确定换算时返回 `status: "review"`，前端保留原始值并提示人工核对，不静默猜测。

### `check_interaction`

请求：

```json
{
  "medications": [{"drug_name": "阿托伐他汀 10 mg"}],
  "indicators": [{"abbreviation": "ALT", "status": "high"}]
}
```

返回：

```json
{
  "status": "review",
  "warnings": [
    {
      "drug": "阿托伐他汀 10 mg",
      "risk": "发现肝酶相关异常，需结合药品说明书与专业人员复核用药风险",
      "source": "阿托伐他汀药品说明书（演示规则）",
      "source_id": "SRC-DRUG-ATORVASTATIN-001",
      "severity": "review"
    }
  ],
  "next_action": "请由专业人员结合说明书复核"
}
```

该工具只产生复核提示，不输出停药、换药或剂量调整建议。真实药品规则接入后，字段结构保持不变。

## `POST /v1/analyze`

请求体：

```json
{
  "report_id": "R001",
  "raw_text": "合成检验单 R001：ALT 68 IU/L；...",
  "medications": "阿托伐他汀 10 mg（合成演示用药）",
  "options": {
    "include_trace": true,
    "include_retrieval": true,
    "include_graph": true
  }
}
```

响应体：

```json
{
  "request_id": "mock-R001",
  "report_id": "R001",
  "status": "success",
  "answer": "演示解读……",
  "items": [
    {
      "indicator_code": "ALT",
      "indicator_name": "丙氨酸氨基转移酶",
      "value": 68.0,
      "unit": "U/L",
      "status": "high",
      "reference_range": {"low": 0, "high": 40},
      "source_id": "SRC-R001-ALT",
      "sources": ["SRC-R001-ALT"]
    }
  ],
  "warnings": [
    {
      "drug": "阿托伐他汀 10 mg",
      "risk": "需要结合异常指标、药品说明书和专业人员意见进一步核查",
      "severity": "review",
      "sources": ["SRC-DRUG-001"]
    }
  ],
  "citations": [
    {
      "id": "来源1",
      "source_id": "SRC-R001-ALT",
      "title": "合成检验单 R001",
      "excerpt": "ALT 68 U/L；参考范围 0—40 U/L",
      "url": "#source-SRC-R001-ALT"
    }
  ],
  "trace_log": [
    {"tool": "parse_report", "status": "done", "elapsed_ms": 120},
    {"tool": "query_reference", "status": "done", "elapsed_ms": 340},
    {"tool": "check_interaction", "status": "done", "elapsed_ms": 280},
    {"tool": "summarize", "status": "done", "elapsed_ms": 190}
  ],
  "retrieval": {
    "strategy": "hybrid",
    "vector_hits": 10,
    "keyword_hits": 5,
    "reranked": 3,
    "sources": [
      {"source_id": "SRC-RANGE-001", "title": "WS/T 405 参考区间", "score": 0.92}
    ]
  },
  "graph": {
    "nodes": [
      {"id": "indicator", "label": "ALT", "kind": "指标"},
      {"id": "reference", "label": "参考范围", "kind": "标准"},
      {"id": "medication", "label": "当前用药", "kind": "用药"}
    ],
    "edges": [
      {"source": "indicator", "target": "reference", "label": "核对"},
      {"source": "indicator", "target": "medication", "label": "需核查"}
    ]
  },
  "knowledge_evidence": {
    "raw_json": "{\"entity\":\"ALT\",\"value\":68}",
    "checked_fields": ["实体名称", "数值与单位", "参考范围", "来源编号"],
    "review_note": "大模型抽取后由人工确认字段，再进入知识库。"
  },
  "meta": {
    "llm_model": "glm-4.7",
    "embedding_model": "embedding-3",
    "rag_config_count": 34
  },
  "disclaimer": "仅用于工程演示，不构成诊断或用药建议。"
}
```

`status` 只表达相对于给定参考范围的 `high`、`low`、`normal` 或 `unknown`，不生成诊断结论，也不提供剂量调整建议。后端可以保留旧的 `trace` 字符串数组，但正式接口建议使用带 `status` 和耗时的 `trace_log` 对象数组。

## MCP 工具联调

项目内置 `phase1/mcp_server/`，包含 `query_reference`、`parse_report`、`evidence_gate`、区间解析器和 34 条参考区间数据。Mock API 会在本地调用同一组工具并把结果放入响应的 `mcp_tools` 字段，保证前端演示链路与 Nexent MCP 链路使用同一套规则。

- 纯规则校验：`python phase1/mcp_server/test_gate.py`
- 端到端校验：`python phase1/mcp_server/e2e_test.py`
- 真实 MCP stdio/HTTP：先用 Python 3.10+ 安装 `phase1/mcp_server/requirements.txt`，再运行 `phase1/mcp_server/run_server.ps1`。


## 脱敏图片演示资产

网页上传区内置 5 个明确标注的脱敏样本，使用 `asset_id` 选择，不把图片内容写入日志：

- `coagulation` / `R007`：图 1 凝血四项，8 个带 ↑↓ 标记的异常指标卡；
- `glucose-crp` / `R008`：图 2 葡萄糖 16.1 mmol/L、C 反应蛋白 16.0 mg/L；
- `mobile` / `R009`：图 3 手机长图，仅验证窄屏图片预览和多模态入口；
- `urine` / `R010`、`liver` / `R011`：图 4、图 5 的结构化演示占位。

图 2 的 `parse_report` 测试文本为：`葡萄糖 16.1 mmol/L；C反应蛋白 16.0 mg/L`，预期两项置信度均为 `0.9`。

## 本地 MCP 工具 HTTP 适配

Flask 前端保留原有 `POST /api/analyze`，并新增三个本地联调入口。它们调用 `phase1/mcp_server/` 中的同名工具，便于浏览器、Postman 或 Nexent 联调：

- `POST /api/tools/query_reference`：`{"indicator":"ALT"}`
- `POST /api/tools/parse_report`：`{"text":"葡萄糖 16.1 mmol/L；C反应蛋白 16.0 mg/L"}`
- `POST /api/tools/evidence_gate`：`{"indicator":"ALT","value":30,"gender":"male"}`
- `POST /api/tools/normalize`：`{"indicator":"HGB","value":11.8,"from_unit":"g/dL","to_unit":"g/L"}`
- `POST /api/tools/check_interaction`：`{"medications":[{"drug_name":"阿托伐他汀"}],"indicators":[{"abbreviation":"ALT","status":"high"}]}`

三态规则由 Python 引擎返回，网页不自行改写门控结论。报告级编排在缺性别或低置信度时进入 `review` 并提供澄清提示；无指标或无参考依据时进入 `abstain`。
