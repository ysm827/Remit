<script setup lang="ts">
import OverlayDetails from "@/pages/team/OverlayDetails.vue";
import type { TeamEvent, TeamState } from "@/apis/teamApi";
import { computed, ref } from "vue";
import RoleAvatar from "./RoleAvatar.vue";
import { roleLabels } from "./roles";

const props = defineProps<{
	events: TeamEvent[];
	expanded?: boolean;
	state?: TeamState | null;
}>();
const limit = ref(30);
const statuses: Record<string, string> = {
	running: "进行中",
	completed: "已完成",
	failed: "执行失败",
	stopped: "已暂停",
	cancelled: "已取消",
	interrupted: "已中断",
	awaiting_approval: "待你验收",
	awaiting_review: "待审阅修改",
	warning: "仍需核验",
	skipped: "已跳过，未验证",
	pending: "待执行",
	needs_info: "待你补充",
	ready: "待开始",
};
const stage = computed(() => {
	const steps = props.state?.steps || [];
	return (
		steps.find((s) => s.id.startsWith("paper:") && s.status === "running") ||
		steps.find((s) => s.id === props.state?.current_node) ||
		steps.find((s) =>
			[
				"running",
				"awaiting_approval",
				"awaiting_review",
				"failed",
				"interrupted",
			].includes(s.status),
		)
	);
});
const latestRole = computed(
	() =>
		stage.value?.role ||
		useful.value.at(-1)?.role ||
		props.events.at(-1)?.role ||
		"coordinator",
);
const isNoise = (event: TeamEvent) =>
	/正在输出|^进度更新$|调用.*工具|^execute_code$|开始执行.*代码|历史执行记录已同步|正在思考下一步|代码手反思纠正错误/.test(
		event.content,
	);
// Only brief action announcements belong in the summary; long reasoning and code stay in details.
const isBriefAction = (event: TeamEvent) =>
	event.content.length <= 240 &&
	/^(接下来|现在|先|继续|正在|已|完成|本轮|检查|读取|计算|生成|验证)/.test(
		event.content.trim(),
	) &&
	!/```|\$\$/.test(event.content);
const useful = computed(() =>
	props.events.filter(
		(event) =>
			!isNoise(event) &&
			!["tool", "progress"].includes(event.kind) &&
			(event.kind !== "agent" || isBriefAction(event)),
	),
);
const short = (text: string, length = 170) =>
	text.length > length ? `${text.slice(0, length)}…` : text;
function progressText(event: TeamEvent) {
	if (event.kind === "plan") {
		const actions: Record<string, string> = {
			resume: "准备继续当前步骤",
			stop: "正在停止任务",
			start: "准备开始建模",
			revise: "准备按修改意见重做",
			write: "准备撰写论文",
			compile: "准备编译论文",
			reply: "整理回复",
			instruct: "已安排下一步工作",
		};
		return actions[String(event.data.action)] || "处理安排";
	}
	const text = event.content
		.replace(/awaiting_review/g, "待审阅修改")
		.replace(/建模ing\.{0,3}/g, "制定建模方案")
		.replace(/\beda\b/gi, "数据清洗与探索分析")
		.replace(/\bques(\d+)\b/g, "问题 $1")
		.replace(/ · (状态更新|步骤完成)$/, "");
	if (event.kind !== "checkpoint") return text;
	// A finished node can coexist with overall running; do not label it running.
	const status =
		!event.data.current_node &&
		Array.isArray(event.data.completed_nodes) &&
		event.data.completed_nodes.length
			? "步骤已结束"
			: statuses[String(event.data.status)];
	return `${text}${status ? ` · ${status}` : ""}`;
}
const latest = computed(() => {
	const last = useful.value.at(-1);
	return last ? progressText(last) : "等待新的阶段进展";
});
const currentDetail = computed(() => {
	const last = useful.value.at(-1);
	if (
		last &&
		/失败|重试|自动修复|重新生成|重新尝试|等待.*(审核|验收)/.test(last.content)
	)
		return progressText(last);
	const boundary =
		[...props.events]
			.reverse()
			.find(
				(e) =>
					e.kind === "checkpoint" &&
					e.data.current_node === props.state?.current_node,
			)?.seq || 0;
	const action = [...useful.value]
		.reverse()
		.find(
			(e) =>
				e.kind === "agent" && e.role === stage.value?.role && e.seq > boundary,
		);
	const routineCodeMessage =
		last && /正在执行.*代码|代码执行完成|代码执行成功/.test(last.content);
	if (last && action && last.seq > action.seq && !routineCodeMessage)
		return progressText(last);
	return action ? progressText(action) : latest.value;
});
const waitingForPaper = computed(
	() =>
		props.state?.status === "completed" &&
		(!props.state.writing?.status ||
			["idle", "ready"].includes(props.state.writing.status)),
);
const headline = computed(() =>
	stage.value
		? short(stage.value.label, 90)
		: waitingForPaper.value
			? "建模已完成，待生成论文初稿"
			: short(latest.value, 110),
);
const stageStatus = computed(
	() =>
		stage.value?.status ||
		(waitingForPaper.value ? "ready" : props.state?.status) ||
		"",
);
const completed = computed(() =>
	(props.state?.steps || []).filter((s) => s.status === "completed").slice(-2),
);
const warnings = computed(() =>
	(props.state?.steps || []).filter((s) =>
		["warning", "skipped"].includes(s.status),
	),
);
const warningIssues = computed(() => [
	...new Set(warnings.value.flatMap((s) => s.issues || [])),
]);
const calls = computed(
	() =>
		props.events.filter((e) => e.kind === "tool" && e.data.input != null)
			.length,
);
const repairs = computed(
	() =>
		props.events.filter((e) =>
			/自动修复|重新生成|重新尝试|正在重试/.test(e.content),
		).length,
);
const milestones = computed(() => {
	const unique = new Map<string, TeamEvent>();
	for (const e of useful.value) {
		if (
			e.kind === "checkpoint" ||
			e.kind === "plan" ||
			e.kind === "preflight" ||
			/正在思考|开始建模|开始制定建模|正在执行.*代码|代码执行完成|代码执行成功/.test(
				e.content,
			)
		)
			continue;
		if (stage.value && progressText(e) === currentDetail.value) continue;
		const text = progressText(e);
		unique.delete(text);
		unique.set(text, e);
	}
	return [...unique.values()].slice(-3);
});
const attention = computed(() => {
	if (stageStatus.value === "awaiting_review")
		return "返修提案已生成，接受后才写入并编译。";
	if (stageStatus.value === "awaiting_approval")
		return "当前步骤正在等待你的验收，请查看下方验收内容。";
	if (
		["failed", "stopped", "interrupted", "cancelled"].includes(
			stageStatus.value,
		)
	)
		return "当前步骤尚未完成，请查看最近的异常信息。";
	return "";
});
const latestAt = computed(() => props.events.at(-1)?.at);
const raw = computed(() => props.events.slice(-limit.value));
const time = (value: string) =>
	new Date(value).toLocaleTimeString("zh-CN", {
		hour: "2-digit",
		minute: "2-digit",
	});

</script>

<template>
 <section class="activity-group" aria-label="执行进度摘要">
  <header class="progress-heading"><RoleAvatar :role="latestRole" compact /><span class="progress-role">{{ roleLabels[latestRole] || 'Remit' }}</span><strong class="progress-label">{{ headline }}</strong><span v-if="statuses[stageStatus]" class="stage-status" :class="{attention: ['failed','warning','awaiting_approval','interrupted'].includes(stageStatus)}">{{ statuses[stageStatus] }}</span></header>
  <div class="progress-detail">
   <p v-if="completed.length" class="completed-line"><span class="detail-label">最近完成</span>{{ completed.map(s => s.label).join('、') }}</p>
   <p v-if="stage && useful.length" class="current-line"><span class="detail-label">当前进展</span>{{ short(currentDetail) }}</p>
   <p v-if="attention" class="attention-note" role="status">{{ attention }}</p>
   <div v-if="warnings.length" class="warning-note"><p><span class="detail-label">仍需核验</span>{{ warnings.map(s => s.label + (s.status === 'skipped' ? '（已跳过，未验证）' : '')).join('、') }}<span v-if="warningIssues.length">（{{ warningIssues.length }} 项）</span></p><OverlayDetails title="待核验事项" v-if="warningIssues.length"><template #trigger>查看待核验事项</template><ul><li v-for="issue in warningIssues" :key="issue">{{ issue }}</li></ul></OverlayDetails></div>
   <ol v-if="milestones.length" class="milestones" aria-label="最近关键进展"><li v-for="event in milestones" :key="event.seq"><span>{{ short(progressText(event)) }}</span><time>{{ time(event.at) }}</time></li></ol>
   <p v-else-if="!stage" class="progress-empty">尚未收到阶段结果；工具调用次数不代表完成进度。</p>
   <footer class="progress-meta"><span v-if="latestAt">最近活动 {{ time(latestAt) }}</span><span v-if="calls">工具调用 {{ calls }} 次</span><span v-if="repairs">自动修复 {{ repairs }} 次</span></footer>
   <OverlayDetails class="raw-log" title="执行明细"><template #trigger>查看执行明细</template>
    <button v-if="events.length > limit" @click="limit += 50">加载更早的日志</button><div class="activity-list"><OverlayDetails title="执行记录" v-for="event in raw" :key="event.seq" class="activity-entry"><template #trigger><span>{{ short(event.content,160) }}</span><time>{{ time(event.at) }}</time></template><pre>{{ event.content }}</pre><pre>{{ JSON.stringify(event.data,null,2) }}</pre></OverlayDetails></div>
   </OverlayDetails>
  </div>
 </section>
</template>

<style scoped>
.activity-group{color:var(--text-color,#292929);margin:22px 0;font-size:13px;line-height:1.65;--progress-muted:var(--text-muted,#666)}
.progress-heading{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.progress-role{font-size:12px;color:var(--progress-muted)}.progress-label{font-size:14px;font-weight:550;min-width:0;overflow-wrap:anywhere}.stage-status{font-size:11px;color:var(--progress-muted);border:1px solid #dedede;border-radius:5px;padding:0 6px}.stage-status.attention{color:#8b4d16;border-color:#d8c7b5}
.progress-detail{margin:12px 0 0 10px;border-left:1px solid #e6e6e6;padding-left:19px}.progress-detail p{margin:7px 0;overflow-wrap:anywhere}.detail-label{color:var(--progress-muted);margin-right:12px;font-size:12px}.warning-note,.attention-note{color:#805323}.warning-note details{font-size:12px}.warning-note summary,.raw-log>summary{cursor:pointer}.warning-note ul{padding-left:18px}.milestones{list-style:none;padding:0;margin:10px 0}.milestones li{display:flex;gap:16px;align-items:baseline;padding:5px 0}.milestones span{flex:1;overflow-wrap:anywhere}time{font-size:11px;white-space:nowrap;color:var(--progress-muted)}.progress-meta{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--progress-muted);margin-top:10px}.raw-log{margin-top:10px;color:var(--progress-muted);font-size:12px}.raw-log button{margin:12px 0;text-decoration:underline}.activity-entry{padding:6px 0}.activity-entry>summary{display:flex;justify-content:space-between;gap:12px;cursor:pointer}.activity-entry pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:360px;overflow:auto;background:#f7f7f7;padding:12px}.progress-empty{color:var(--progress-muted)}summary:focus-visible,button:focus-visible{outline:2px solid currentColor;outline-offset:4px}@media(max-width:640px){.progress-detail{padding-left:12px}.milestones li{gap:8px}.progress-label{flex-basis:100%;margin-left:30px}.stage-status{margin-left:30px}}
</style>
