# MedTrace · Nexent 医疗检验报告解读 Demo

这是华为 ICT 杯赛题 3 的阶段性演示项目：检验报告结构化解析、参考范围核对、用药核查和可溯源决策门控。当前示例使用明确标注的合成数据，默认运行 Mock API，不包含真实患者信息。

## 本地运行

在 `phase1` 目录启动：

```powershell
python mock_nexent_api.py
python app.py
```

浏览器打开 `http://127.0.0.1:5050`。

## 当前演示案例

结果区提供“通过 / 复核（版本冲突）/ 复核（缺性别）/ 拒答”四个视图，后端只有 pass/review/abstain 三态。性别补充、来源比较、审计时间轴与加载反馈已接入。共享页使用明确标注的离线样本，真实 Nexent 服务仍需配置。详情见 `phase1/docs/gate_ui_release.md`。

## 图片上传（2026-11-23）

已准备真实文件预览、multipart 上传代理、Nexent v1.8 附件与 Agent SSE 适配，以及失败不回退假数据的处理。传输测试使用本地模拟服务，**真实 OCR 尚未接通**：队友反馈镜像源损坏，当前没有可用服务地址与 Agent ID。Pages 上的图1–图5是预置数据演示，自行上传的文件不会按名称套用样例结果。

恢复服务后的配置、版本核对、免费共享网页接法与验收见 [图片上传接入与联调](phase2/图片上传接入与联调.md)，服务端变量见 `.env.example`。

- `R001/R002/R003`：基础合成检验单；
- `R004`：`parse_report` 字段规范测试；
- `R005`：来源冲突与证据决策门控测试；
- `R006`：无指标证据不足（`abstain`）测试；
- `R007`：脱敏图 1 凝血四项，8 个 ↑↓ 异常指标卡；
- `R008`：脱敏图 2 葡萄糖 16.1 + C 反应蛋白 16.0 解析测试；
- `R009`：脱敏图 3 手机长图兼容性预览，`R010/R011` 为图 4/5 结构化预览。
- `R012`：V2 回归案例，男性 ALT=200 U/L，置信度 0.95，来源为 WS/T 404.1-2012。
- `R013`：缺少性别的追问案例；补充后重新分析同一报告。

## 部署

仓库包含 `Dockerfile` 和 `render.yaml`，可在 Render 中选择该仓库并创建 Web Service。部署后会获得固定的 `onrender.com` 地址；环境变量默认使用合成数据 Demo 模式。接入真实 Nexent 时，再配置 `APP_MODE=real`、`NEXENT_API_URL` 和 `NEXENT_API_KEY`，不要把 Key 写进代码或网页。

## 目录

- `phase1/`：Flask 前端、Mock API、合成数据、图表和接口文档；
- `phase2/`：Nexent HTTP 客户端；
- `phase1/docs/api_contract.md`：字段协议和证据门控协议；
- `phase1/docs/real_data_plan.md`：公开脱敏数据使用边界；
- `phase1/docs/phase2_ready_checklist.md`：阶段二接口、数据和验收清单；
- `phase1/docs/system_prompt_v2.md`：Nexent Agent 的 V2 安全提示词和三态输出边界；
- `phase1/mcp_server/`：`query_reference`、`parse_report`、`normalize`、`check_interaction`、`evidence_gate`、区间解析、34 条参考区间和验证脚本；
- `docs/static/assets/medical-demo/`：明确标注的脱敏图片演示资产。


## MCP 工具验证

```powershell
python phase1/mcp_server/test_gate.py
python phase1/mcp_server/e2e_test.py
```

阶段二新增的本地联调入口：

- `POST /api/tools/normalize`：单位标准化；
- `POST /api/tools/check_interaction`：用药与异常指标规则核查。

`NEXENT_API_URL` 对应本项目约定的 JSON 文本适配器，不能直接假设它是 Nexent 原生接口。图片链路单独配置 `NEXENT_BASE_URL` 与 `NEXENT_IMAGE_AGENT_ID`，使用官方 v1.8 协议；恢复服务后还需核对实际部署版本。

在没有 `fastmcp` 的 Python 环境中，端到端脚本会自动执行同一工具链的离线校验；安装 `phase1/mcp_server/requirements.txt` 后可切换到真实 MCP stdio/HTTP 传输。
