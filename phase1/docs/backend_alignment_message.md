# 发给后端的对齐消息

赖同学，前端现在需要按下面结构联调。请求体包含 `report_id`、`raw_text`、`medications` 和 `options`；响应请至少保留：

- `items`：指标、数值、单位、`status`、参考范围、`sources`；
- `warnings`：当前用药、需要核查的风险、严重级别和来源；
- `citations`：来源编号、标题、摘录和跳转标识；
- `trace_log`：`tool`、`status`、`elapsed_ms`，覆盖 `parse_report`、`query_reference`、`check_interaction`、`summarize`；
- `retrieval`：向量召回数、关键词召回数、重排后数量、来源和 `score`；
- `graph`：知识关联网络的 `nodes` 和 `edges`；
- `meta`：`llm_model=glm-4.7`、`embedding_model=embedding-3`、RAG 配置数量。

这样前端可以同时展示应用价值、可溯源、RAG 技术证据和 MCP 编排过程。真实 API 地址、认证方式和最终字段命名请在 11/20 接口冻结前确认。
