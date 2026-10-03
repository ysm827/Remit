<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getExecutionBudget, resumeWithExecutionBudget, type ExecutionBudgetSnapshot } from "@/apis/teamApi";
import { explainModelingSubmissionFailure } from "@/apis/submitModelingApi";

const props = defineProps<{ taskId: string; nodeId: string | null; sending: boolean }>();
const emit = defineEmits<{ resumed: [] }>();
const snapshot = ref<ExecutionBudgetSnapshot | null>(null);
const additional = ref(12);
const busy = ref(false);
const error = ref("");
let version = 0;
let requestId = "";
const valid = computed(() => Number.isInteger(additional.value) && additional.value >= 1 && additional.value <= 48);
function reset() {
	version++;
	snapshot.value = null;
	error.value = "";
	busy.value = false;
	additional.value = 12;
	requestId = "";
}
watch(() => [props.taskId, props.nodeId], reset);
watch(additional, () => { requestId = ""; });
onBeforeUnmount(() => { version++; });

async function review() {
	if (busy.value || props.sending) return;
	const current = ++version;
	busy.value = true;
	error.value = "";
	snapshot.value = null;
	requestId = "";
	try {
		const { data } = await getExecutionBudget(props.taskId);
		if (current !== version) return;
		if (data.node_id !== props.nodeId) throw new Error("当前阶段已变化，请刷新项目后再查看。");
		snapshot.value = data;
	} catch (cause) {
		if (current === version) error.value = explainModelingSubmissionFailure(cause);
	} finally {
		if (current === version) busy.value = false;
	}
}
async function confirm() {
	const reviewed = snapshot.value;
	if (!reviewed || busy.value || props.sending || (reviewed.remaining === 0 && !valid.value)) return;
	const current = version;
	busy.value = true;
	error.value = "";
	requestId ||= crypto.randomUUID().replaceAll("-", "");
	try {
		await resumeWithExecutionBudget(props.taskId, reviewed.node_id, reviewed.remaining > 0 ? undefined : {
			confirmed: true,
			request_id: requestId,
			stage_key: reviewed.stage_key,
			expected_used: reviewed.used,
			expected_limit: reviewed.limit,
			additional: additional.value,
		});
		if (current !== version) return;
		reset();
		emit("resumed");
	} catch (cause) {
		if (current === version) error.value = explainModelingSubmissionFailure(cause);
	} finally {
		if (current === version) busy.value = false;
	}
}
</script>
<template>
	<div class="budget-recovery">
		<button type="button" :disabled="busy || sending" @click="review">{{ snapshot || error ? '重新查看执行次数' : '查看执行次数并继续' }}</button>
		<p v-if="busy && !snapshot" role="status">正在读取本阶段记录…</p>
		<div v-if="snapshot" class="budget-review" aria-label="确认本阶段执行次数">
			<p>{{ snapshot.label }}：已记录 {{ snapshot.used }} 次执行预占，上限 {{ snapshot.limit }} 次。失败或中断的尝试也可能计入。</p>
			<template v-if="snapshot.remaining === 0">
				<label>追加执行次数 <input v-model.number="additional" type="number" min="1" max="48" step="1" :disabled="busy || sending" /></label>
				<p v-if="valid">确认后仅将本阶段上限调整为 {{ snapshot.limit + additional }} 次，保留已有计数与成果。</p>
				<p v-else role="alert">请输入 1 至 48 之间的整数。</p>
			</template>
			<p v-else>本阶段还有 {{ snapshot.remaining }} 次可用，无需追加。</p>
			<p>继续运行可能调用你配置的模型并产生费用。追加次数不代表已有结果通过审核。</p>
			<div class="budget-actions">
				<button type="button" :disabled="busy || sending || (snapshot.remaining === 0 && !valid)" @click="confirm">{{ busy ? '正在提交…' : snapshot.remaining > 0 ? '继续当前阶段' : '确认追加并继续' }}</button>
				<button type="button" :disabled="busy" @click="reset">取消</button>
			</div>
		</div>
		<p v-if="error" role="alert">{{ error }} 可重新查看当前记录；已保存成果不受影响。</p>
	</div>
</template>
<style scoped>
.budget-recovery{margin:8px 0}.budget-review{border:1px solid #d8dfce;background:#fff;padding:12px;margin-top:8px;border-radius:6px}.budget-review p{margin:0 0 8px}.budget-review label{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.budget-review input{width:80px;padding:5px;border:1px solid #b8c1ad;border-radius:4px}.budget-actions{display:flex;gap:8px;flex-wrap:wrap}button{background:white;padding:5px 9px;border:1px solid #d8dfce;border-radius:5px;color:#404b35}button:disabled{opacity:.5}button:focus-visible,input:focus-visible{outline:2px solid #65783e;outline-offset:3px}
</style>
