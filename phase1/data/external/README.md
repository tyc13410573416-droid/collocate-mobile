# 外部公开数据样本

这里的文件用于 `parse_report`、区间解析和 OCR 演示，不包含真实患者身份信息。

## 1. `lab_test_results_anonymized_cc0.csv`

- 来源：[Kaggle · Laboratory Test Results – Anonymized Dataset](https://www.kaggle.com/datasets/pinuto/laboratory-test-results-anonymized-dataset)
- 内容：28 条匿名化检验结果，包含项目名、结果、单位、参考区间和 Normal/High/Low 状态。
- 许可：压缩包内 `metadata.json` 声明为 **CC0 1.0**；Kaggle 页面当前显示 **CC BY-SA 4.0**。为稳妥起见，公开再分发时按 Kaggle 页面较严格的 CC BY-SA 4.0 处理，并保留来源链接。
- 备注：该文件适合结构化字段和三态门控测试；原始文本包含土耳其语项目名/备注，接入中文解析前应做术语映射。

## 2. `gritworks-lab-report/`

- 来源：[Hugging Face · GritWorks Diagnostics Lab Documents](https://huggingface.co/datasets/Gritworks/synthetic-lab-report-ocr-sample)
- 内容：一份虚构的 CD4/CD8 + CBC 检验单，提供清晰版和低光版 PNG，以及对应 JSON 标注。
- 许可：**CC BY 4.0**，署名 `GritWorks (gritworks.ai)`。
- 备注：这是合成数据，不是真实患者数据；适合 OCR/图片上传演示。JSON 中含虚构姓名和编号，不能把它误称为真实脱敏病例。

## 使用边界

这些文件只用于比赛演示、软件测试和研究。页面展示时应保留“合成/公开数据”标识，不输出诊断或剂量调整建议。
