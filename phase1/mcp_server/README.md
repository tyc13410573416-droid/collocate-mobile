# MedTrace 医疗智能体 MCP Server

这是项目内置的 MCP 工具服务端，把“查参考区间 / 解析检验单 / 三态证据门控”封装成 Nexent 可调用的工具。网页 Mock API 与这里使用同一套 Python 规则。

## 工具

| 工具 | 作用 | 关键返回 |
|---|---|---|
| `query_reference` | 查参考区间 | `source_id` / `source_version` / `gender_range` |
| `parse_report` | 解析检验单文本 | 指标名、数值、单位、`confidence` |
| `normalize` | 单位标准化 | 原值/原单位、标准值/标准单位、换算因子、`status` |
| `check_interaction` | 用药与异常指标核查 | `warnings`、`source_id`、`next_action` |
| `evidence_gate` | 三态判定 | `decision_gate`、`confidence`、`evidence_status`、`conflicts`、`next_action`、`source_versions` |

## 文件

- `server.py`：MCP 主入口，支持 stdio 和 streamable HTTP；
- `range_parser.py`：分性别、年龄备注、单侧上/下限和通用区间解析；
- `gate_engine.py`：确定性的三态规则引擎；
- `data/references.json`：34 条参考区间知识库；
- `test_gate.py`：区间解析、三态、图 2 双指标、单位和用药核查单测；
- `e2e_test.py`：有 `fastmcp` 时走真实 stdio，没有时走离线工具链校验；
- `requirements.txt`：真实 MCP transport 的可选依赖。

## 验证

在仓库根目录执行：

```powershell
python phase1/mcp_server/test_gate.py
python phase1/mcp_server/e2e_test.py
```

当前演示机只有 Python 3.7，因此测试会自动走离线模式；所有业务规则不依赖 `fastmcp`。真实 stdio/HTTP 接入 Nexent 时，请使用 Python 3.10+：

```powershell
python -m pip install -r phase1/mcp_server/requirements.txt
python phase1/mcp_server/server.py --http 3001
```

Nexent Docker 内连接地址：`http://host.docker.internal:3001/mcp`。服务需监听 `0.0.0.0`；不要在前端代码中写 API Key。

## 三态约定

- `pass`：证据唯一且一致，允许展示带来源结果；
- `review`：发现缺性别、低置信度或来源冲突；缺性别可由前端追问后重新核对；
- `abstain`：没有可识别指标或没有可用参考依据，停止输出确定性解读。

`source_version` 和 `effective_date` 当前是演示占位字段，知识库 v2 到位后只替换数据，不改变接口结构。
