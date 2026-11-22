# 门控界面使用与验收

结果区提供四个“一键演示”按钮，仍使用后端三态 `pass / review / abstain`，没有新增第四个后端枚举。

| 按钮 | 样本 | 预期行为 |
| --- | --- | --- |
| 正常通过 | R012：男性 ALT 200 U/L | 绿色横幅、带来源解读；通过只说明证据允许输出，不表示指标正常 |
| 证据冲突 | R005：ALT 45 U/L | 橙色横幅、两套参考范围并列；来源 A/B 明确标注合成数据，不冒充正式标准修订 |
| 缺少信息 | R013：ALT 68 U/L，未提供性别 | 橙色横幅、性别选择弹窗；提交后重新分析同一报告，选择女性时采用对应区间 |
| 查无此项 | R006：无可识别指标 | 灰色横幅，隐藏解读卡片、图谱和推理链，保留审计记录与免责声明 |

四种状态均支持折叠的“查看AI决策审计轨迹”。演示记录来自 Python 演示引擎，不是模型内部思考。真实接口返回的 `trace_log`（包含 `step / status / detail`）也可直接展示。

## 共享页与本地服务

- GitHub Pages 使用明确标注的离线样本，仅接受已支持的报告文本和用药组合。修改样本内容后会提示接入真实 API，不再按编号套用旧结果。
- `stage2-demo.js` 按报告内容、性别、用药选择对应样本结果，绝不把实际 API 故障伪装成成功。
- Flask 使用 `docs/static` 的同一份界面资源；真实模式通过服务器代理向 Nexent 发起请求。
- 图片快捷样本仍为结构化演示。未接入任意图片/PDF OCR，上传未知文件会明确提示，不自动载入 R001。

## 构建与测试

修改样本或后端演示规则后执行：

```powershell
python phase1/scripts/build_gate_demo.py
python -m unittest phase1/test_prompt_contract.py phase2/test_nexent_client.py phase2/tests/test_gate_flow.py
python phase1/mcp_server/test_gate.py
```

浏览器专项脚本：`phase2/tests/gate-ui.browser.js`，使用 Playwright CLI 的 `run-code --filename` 执行。启动静态测试页：`python -m http.server 8876 --bind 127.0.0.1 --directory docs`。

专项验收覆盖：四态切换、加载反馈、男女字段传递、补充性别、来源展开、审核中性展示、拒答清空、修改输入拦截、真实 API 502 报错、1440/1024/820/768/390/320 宽度适配。通用整站设计检查器输出 `GATE: OFF (no build active)`，未把该输出当作验收通过。
