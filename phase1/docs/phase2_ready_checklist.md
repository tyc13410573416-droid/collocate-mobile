# 阶段二联调就绪清单

目标：在 11 月 21–25 日把“输入报告 → 真实工具编排 → 带来源结果”跑通。网页现有 Mock 链路继续保留，等待正式 Nexent 地址后只替换配置。

## 已可直接联调

- `POST /api/tools/query_reference`
- `POST /api/tools/parse_report`
- `POST /api/tools/normalize`
- `POST /api/tools/check_interaction`
- `POST /api/tools/evidence_gate`
- `POST /api/analyze`

## 待队友提供

1. Nexent 正式 API URL、传输方式和鉴权方式；
2. 正式响应 JSON，字段至少包含 `lab_results`、`medications`、`warnings`、`citations`、`trace_log`、`decision_gate`；
3. `normalize` 的正式换算表；
4. `check_interaction` 的药物规则、来源编号、版本和生效日期；
5. 至少 30 份测试样本及标准 JSON，覆盖图片、文本、缺性别、低置信度和来源冲突；
6. 允许公开展示的图片/PDF许可证和数据资产台账。

## 通过条件

- 真实接口返回无效字段时，页面显示错误提示，不白屏；
- `value` 为数值，`status` 只允许 `high/low/normal/unknown`；
- 未知单位不自动猜测，进入 `review`；
- 用药警示必须带 `source_id`，只显示复核提示；
- 缺性别、来源冲突和低置信度均能展示门控状态；
- 30 份样本中每份结果都保留引用和调用链。

## 本地验证

```powershell
python phase1/mcp_server/test_gate.py
python phase1/mcp_server/e2e_test.py
python -m unittest phase2/test_nexent_client.py
```
