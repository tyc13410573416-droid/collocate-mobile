# 阶段一交付物

这套原型对应冲刺表中汤永超的阶段一任务：前端假数据演示、数据清洗脚本、初版图表、Mock 联调和可点击溯源展示。

## 目录

- `app.py`：前端原型与 API 代理，默认运行在 `http://127.0.0.1:5050`。
- `mock_nexent_api.py`：模拟 Nexent 分析接口，默认运行在 `http://127.0.0.1:5051`。
- `analysis_engine.py`：前端和 Mock 服务共用的安全演示分析逻辑。
- `scripts/generate_demo_data.py`：生成可复现的合成检验单数据。
- `scripts/clean_medical_data.py`：单位统一、去重、异常方向标记和数据资产字段整理。
- `scripts/generate_charts.py`：生成 3 张可放入初赛文档的初版图表。
- `data/raw/inspection_reports.json`：10 份合成检验单，明确标注 `synthetic=true`。
- `data/cleaned/inspection_reports_cleaned.csv`：清洗后的结构化表格。
- `data/cleaned/cleaning_summary.json`：清洗统计和单位转换记录。
- `charts/`：初版图表。
- `templates/`、`static/`：前端页面。
- `docs/api_contract.md`：Mock API 接口约定。
- `docs/real_data_plan.md`：公开脱敏数据的选型、合规边界和接入方案。

## 生成数据与图表

在 `phase1` 目录执行：

```powershell
python scripts/generate_demo_data.py
python scripts/clean_medical_data.py
python scripts/generate_charts.py
```

脚本只处理合成演示数据，不包含真实个人信息。清洗脚本会把 `IU/L`、`g/dL`、`mg/dL` 等输入统一为规范单位，并按 `report_id + indicator_code` 去重。

## 启动假数据演示

先启动 Mock Nexent 服务，再启动前端：

```powershell
python mock_nexent_api.py
python app.py
```

打开 `http://127.0.0.1:5050`。页面左侧输入区预置了 R001 合成报告，点击“生成带来源解读”后，右侧会显示结果摘要、异常方向、调用链和 `[来源1]`、`[来源2]` 等可点击引用。若 Mock 服务未启动，前端会自动使用同一套本地演示逻辑，页面仍可完成假数据演示。

如需让同一局域网的组员查看，可在启动前端时绑定局域网网卡：

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "5050"
python app.py
```

然后用 `ipconfig` 查到本机 IPv4 地址，让组员访问 `http://本机IPv4:5050`。这只适用于同一局域网；当前演示使用合成数据，真实 API Key 不要写进前端页面或发给组员。

如需让不同网络的组员临时查看，可运行 `share_demo.ps1`。脚本会检查并启动本地服务，然后创建一个临时公网链接；保持脚本窗口运行，关闭窗口后链接会失效。

前端会在本地 `logs/access.jsonl` 记录页面和分析接口的访问时间、路径、状态码和匿名访客标识，不保存原始 IP 或报告文本。查看统计：

```powershell
python scripts/access_summary.py
```

## 阶段一验收对应关系

| 排期要求 | 本目录中的证据 |
| --- | --- |
| UI 假数据可演示 | `app.py` + `templates/index.html` + `static/` |
| 数据清洗脚本 v1 | `scripts/clean_medical_data.py` |
| 2—3 张初版图表 | `charts/abnormal_rate.png`、`charts/status_distribution.png`、`charts/normalized_units.png` |
| Mock 联调 | `app.py` 的 `/api/analyze` + `mock_nexent_api.py` 的 `/v1/analyze` |
| 引用编号可点开来源 | 页面右侧引用列表和来源卡片 |
| 数据资产标识 | 清洗 CSV 中的 `synthetic`、`source`、`version_year`、`modality`、`source_id` 字段 |

## 脱敏图片样本

`docs/static/assets/medical-demo/` 保存了用户提供的脱敏演示图片。前端上传区提供图 1–5 的快捷选择，并在提交时携带 `asset_id`；图 1 展示 8 个 ↑↓ 异常指标卡，图 2 使用明确标注的葡萄糖/C 反应蛋白结构化结果，图 3 用于手机长图预览，图 4/5 提供结构化演示占位。图片不写入访问日志，页面结果仍带“仅用于工程演示”声明。
