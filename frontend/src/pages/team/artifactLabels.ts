const labels: Record<string, string> = {
	check: "检查内容",
	threshold: "判定阈值",
	questions_solution: "分题方案",
	eda: "数据检查与清洗",
	sensitivity_analysis: "灵敏度与稳健性分析",
	quality_report: "结果校验",
	modeler_review: "建模复核",
	coder_response: "计算说明",
	grounding_values: "计算依据",
	summary: "结论说明",
	content: "内容",
	analysis: "分析",
	result: "结果",
	results: "结果",
	solution: "求解过程",
	conclusion: "结论",
	selected_model: "采用方法",
	candidate_models: "候选方法",
	problem_type: "问题类型",
	assumptions: "模型假设",
	limitations: "局限与注意事项",
	remaining_uncertainties: "尚未确定的问题",
	checks: "逐项检查",
	status: "报告状态",
	verdict: "复核结论",
	evidence: "依据",
	strengths: "已确认的内容",
	weaknesses: "仍需关注",
	writer_guidance: "论文表述建议",
	manual_review_note: "需要确认的差异",
	manual_review_required: "报告是否要求人工复核",
	failure_reason: "检查说明",
	revision_plan: "修改建议",
	type_specific: "数据概况",
	unit_check_note: "单位核验说明",
	unit_mapping_artifact: "单位对照文件",
	independent_unit: "独立分析单位",
	data_leakage_checks: "数据使用检查",
	robustness_checks: "稳健性检查",
	raw_rows: "原始记录数",
	cleaned_rows: "整理后记录数",
	missingness_checked: "已检查缺失值",
	duplicates_checked: "已检查重复项",
	outliers_assessed: "异常值评估",
	independent_unit_identified: "已明确分析单位",
	dem_dims_and_nodata: "地形栅格与无效值",
	node_elevation_extract_rate: "节点高程提取",
	cargo_uniqueness: "货箱编号唯一性",
	segment_computable: "航段可计算性",
	unit_consistency: "单位一致性",
	cruise_above_ground: "巡航净空",
	cargo_deadline_consistency: "货箱时限一致性",
	node_alt_uses_dem: "节点高程一致性",
	passed: "是否通过",
	value: "数值",
	note: "说明",
	name: "名称",
	path: "文件路径",
	artifacts: "相关文件",
	paper_ready_images: "结果图表",
	metrics: "评价指标",
	metric: "指标",
	metric_name: "指标",
	metric_value: "数值",
	unit: "单位",
	description: "说明",
	baseline: "基准值",
	current: "当前值",
	improvement: "改善幅度",
	formula: "公式",
	variables: "变量",
	constraints: "约束条件",
	objective: "目标",
	method: "方法",
	steps: "步骤",
};
export function artifactLabel(key: string): string {
	const question = key.match(/^ques(?:tion)?_?(\d+)$/i);
	return question
		? `问题 ${question[1]}`
		: labels[key] || key.replace(/_/g, " ");
}
export function asRecord(value: unknown): Record<string, unknown> {
	return value && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}
export function readableValue(value: unknown, field = ""): string {
	if (value == null || value === "") return "未提供";
	if (typeof value === "boolean") return value ? "是" : "否";
	if (field === "problem_type" && value === "eda") return "数据检查与清洗";
	if (["status", "verdict", "result"].includes(field)) {
		const statuses: Record<string, string> = {
			pass: "通过",
			fail: "未通过",
			passed: "检查通过",
			refined: "修正后通过",
			needs_review: "需关注",
			manual_review: "报告建议人工复核",
			failed: "未通过",
			completed: "已完成",
		};
		return statuses[String(value)] || String(value);
	}
	return value === "not_applicable" ? "不适用" : String(value);
}
