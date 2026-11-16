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

`decision_gate` 只能是 `pass`、`review` 或 `abstain`。当来源版本冲突、患者关键信息缺失或抽取置信度低于 0.8 时，返回 `review`；没有足够指标和参考范围时返回 `abstain`。前端会显示门控状态、冲突字段和下一步动作，不把复核状态包装成诊断结论。

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
