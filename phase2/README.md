# 阶段二交付物

阶段二把阶段一的页面接入严格的 Nexent-compatible HTTP 客户端，补齐错误态和最终图表。前端在 `APP_MODE=real` 时不会再静默回退到本地演示逻辑：接口不可用会返回 502，并在页面显示联调失败原因。

## 真实 API 模式

先准备 Nexent API 地址，再启动阶段一前端：

```powershell
cd C:\Users\tyc\Documents\ChatGPT\华为
$env:APP_MODE = "real"
$env:NEXENT_API_URL = "https://your-nexent-host/v1/analyze"
$env:NEXENT_API_KEY = "your-token"
python phase1/app.py
```

前端会发送 `report_id` 和 `raw_text`，并要求响应包含 `answer`、`items`、`citations`、`trace` 四个字段。引用编号继续通过页面中的来源卡片点击查看。

本地联调验收可以把 `NEXENT_API_URL` 指向阶段一的兼容接口：

```powershell
cd C:\Users\tyc\Documents\ChatGPT\华为\phase1
python mock_nexent_api.py
```

另开终端设置 `APP_MODE=real` 后运行 `python app.py`，页面状态应显示“Mock API 已联通”，响应中的 `transport` 为 `nexent-http`。

## 最终图表

```powershell
cd C:\Users\tyc\Documents\ChatGPT\华为
python phase2/scripts/generate_final_charts.py
```

输出到 `phase2/charts/` 的 5 张图表分别覆盖异常率、状态分布、单位规范化、样本完整度和指标数值分布。
