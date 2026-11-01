# 第二位真人独立标注包

请仅将本目录交给标注者。包含150条既有工程输入，顺序已打散，未包含原有标签、规则或模型预测。它用于独立标注对账，不能声称是从未使用过的新盲测集。

## 填写方式

用支持UTF-8的表格软件打开reviewer-B.tsv。只填写四个标签列、reviewed、annotator_id及note；不要修改case_id和text。

- cognitive_demand：recall / comprehend / apply / analyze / evaluate / create，最多3项，多项按任务顺序用 `|` 分隔。
- self_report：none / confused / stuck / understood，最多1项。
- difficulty_locus：comprehension / discrimination / procedure / memory / pace，最多1项；最终允许取值以label-definitions.json为准。
- engagement：最终取值见label-definitions.json，最多1项。
- 无法确定时标签列留空，这是审核后的弃权，不填unknown。
- 每条确实阅读并独立判断后，reviewed改为1；annotator_id填写标注者代号，例如reviewer-B。未完成条目保留0。
- 不查看既有标签、规则代码或模型结果；不推断掌握度、成绩、长期偏好或具体误区。需要上下文才能判断时弃权并说明。

输入只提供原句，因此“懂了”“不会做”等可以自报；没有给出实际题目和答案时，不能推断回答正确与否。

## 导入与对账

由工程窗口在应用目录执行（输出应使用新文件名）：

```powershell
.venv-runtime/Scripts/python.exe -B scripts/import_semantic_annotations.py <填写完成的reviewer-B.tsv> <新的B.jsonl>
.venv-runtime/Scripts/python.exe -B scripts/annotation_agreement.py <第一位真人的A.jsonl> <B.jsonl>
```

导入器拒绝未审核样本、缺少标注者代号、未知标签、重复标签或重复case_id。两份文件必须使用同批case_id才能对账。

现有参考标签的来源是工程标注，尚无可核实的第一位真人独立标注文件。B与工程参考对账只可称“真人与工程标签一致性”；报告人际κ需要两位真人各自独立完成的同批文件及标注者记录。不得为凑完成度复制参考标签。

当前状态：待第二位真人实际填写，尚未完成独立标注。
