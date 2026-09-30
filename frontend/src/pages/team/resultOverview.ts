import { artifactLabel, asRecord } from "./artifactLabels";

export type ResultMetric = { name: string; value: string; baseline?: string };
export function plainExcerpt(value: unknown, limit = 180): string {
 if (typeof value !== "string") return "";
 const text = value.replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/[#*`>|]/g, "").replace(/\s+/g, " ").trim();
 return text.length > limit ? text.slice(0, limit) + "…" : text;
}
const scalar = (v: unknown) => typeof v === "number" || typeof v === "string" ? String(v) : "";
export function resultOverview(key: string, value: unknown) {
 const record = asRecord(value), report = asRecord(record.quality_report);
 const summary = asRecord(record.execution_summary), review = asRecord(record.modeler_review);
 const specific = asRecord(report.type_specific);
 const checks = Object.values(asRecord(report.checks)).concat(Array.isArray(report.robustness_checks) ? report.robustness_checks : []);
 const statuses = [summary.status, summary.modeler_verdict, review.verdict, report.status];
 const failed = statuses.some(s => ["fail", "failed", "reject"].includes(String(s)));
 const attention = failed || report.manual_review_required === true || checks.some(c => asRecord(c).passed === false) || statuses.some(s => ["manual_review", "needs_review", "revise"].includes(String(s)));
 const reviewed = [review.verdict, summary.modeler_verdict].some(s => ["accept", "pass", "passed", "refined"].includes(String(s)));
 const tone = attention ? "attention" : reviewed ? "reviewed" : "pending";
 const status = failed ? "校验未通过" : attention ? "待核验" : reviewed ? "复核通过" : "已记录 · 待复核";
 const metrics: ResultMetric[] = [];
 const names: Record<string,string> = { trips: "运输架次", energy_kWh: "能耗（kWh）", cumulative_job_time_s: "累计作业时间（s）", makespan_s: "完工时间（s）" };
 for (const [name, raw] of Object.entries(asRecord(specific.objectives_detail))) {
  const m = asRecord(raw), current = scalar(m.model ?? m.model_value ?? m.value);
  if (current) metrics.push({name: names[name] || artifactLabel(name), value: current, baseline: scalar(m.baseline ?? m.baseline_value) || undefined});
 }
 if (!metrics.length && Array.isArray(summary.metrics)) for (const raw of summary.metrics) {
  const m = asRecord(raw), current = scalar(m.value ?? m.current ?? m.model_value);
  if (current) metrics.push({name: String(m.name ?? m.metric ?? "已记录指标") + (m.unit ? `（${m.unit}）` : ""), value: current, baseline: scalar(m.baseline ?? m.baseline_value) || undefined});
 }
 const objective = asRecord(specific.objective);
 if (!metrics.length && scalar(objective.model_value)) metrics.push({name: "目标函数值", value: scalar(objective.model_value), baseline: scalar(objective.baseline_value) || undefined});
 const response = record.coder_response;
 const narrative = typeof response === "string" ? response : asRecord(response).code_response;
 const conclusion = record.conclusion ?? report.conclusion ?? summary.conclusion;
 const narrativeText = typeof narrative === "string" ? narrative : "";
 // Prefer the author's result section to introductory debugging notes. Never invent a conclusion.
 const match = narrativeText.match(/^#{1,3}[^\n]*(?:核心结果|关键结果|主要结果)[^\n]*\n([\s\S]*?)(?=^#{1,3}\s|$(?![\s\S]))/m);
 const sourceText = typeof conclusion === "string" ? conclusion : match?.[1] || narrativeText;
 const excerpt = plainExcerpt(sourceText) || "尚未保存可直接阅读的结论，请查看计算说明与核验依据。";
 const warning = plainExcerpt(review.summary ?? summary.modeler_summary ?? report.manual_review_note ?? report.failure_reason, 200);
 const related = [...new Set([record.artifacts, report.artifacts, summary.artifacts, record.paper_ready_images, report.paper_ready_images, summary.paper_ready_images].flatMap(v => Array.isArray(v) ? v.filter((n): n is string => typeof n === "string") : []))];
 return { key, title: artifactLabel(key), record, report, summary, review, metrics, status, tone, excerpt, narrative: narrativeText, warning, related,
  method: plainExcerpt(summary.selected_model ?? report.selected_model, 150),
  activity: plainExcerpt(summary.run_summary ?? summary.content, 180) };
}
