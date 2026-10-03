<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{ sections: string[]; disabled: boolean }>();
const emit = defineEmits<{
	revise: [request: { sections: string[]; instructions: string }];
}>();
const open = ref(false);
const selected = ref<string[]>([]);
const instructions = ref("");
const names: Record<string, string> = {
	eda: "数据分析",
	sensitivity_analysis: "稳定性分析",
	firstPage: "摘要",
	RepeatQues: "问题重述",
	analysisQues: "问题分析",
	modelAssumption: "模型假设",
	symbol: "符号说明",
	judge: "结论与局限",
};
const affected = computed(() =>
	selected.value.some((key) =>
		/^(eda|ques\d+|sensitivity_analysis)$/.test(key),
	),
);
const canSubmit = computed(
	() =>
		!props.disabled &&
		selected.value.length > 0 &&
		instructions.value.trim().length > 0 &&
		selected.value.every((key) => props.sections.includes(key)),
);
function submit() {
	if (canSubmit.value)
		emit("revise", {
			sections: [...selected.value],
			instructions: instructions.value.trim(),
		});
}
</script>
<template>
	<section class="chapter-revision">
		<button :disabled="disabled" :aria-expanded="open" @click="open = !open">{{ open ? '收起章节返修' : '按章返修' }}</button>
		<form v-if="open" @submit.prevent="submit">
			<p>沿用上一轮模型章节，只重写所选内容。完成后先审阅差异，接受后才写入并编译；已有源码和计算证据保留。</p>
			<fieldset :disabled="disabled"><legend>选择返修章节</legend><label v-for="key in sections" :key="key"><input v-model="selected" type="checkbox" :value="key" />{{ names[key] || (/^ques\d+$/.test(key) ? `问题 ${key.slice(4)}` : key) }}</label></fieldset>
			<p v-if="affected">修改计算相关章节时，会一并更新摘要、结论及其他前置说明，使全文保持一致。</p>
			<label>本次返修意见<textarea v-model="instructions" :disabled="disabled" maxlength="10000" aria-label="本次章节返修意见" placeholder="指出需要纠正的表述、证据文件和期望的解释。" /></label>
			<button type="submit" :disabled="!canSubmit">生成返修提案</button>
		</form>
	</section>
</template>
<style scoped>
.chapter-revision{padding:8px 18px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#536248}.chapter-revision button{border:1px solid #dce2d5;border-radius:5px;padding:5px 9px;background:#fafbf8}.chapter-revision button:disabled{opacity:.5}.chapter-revision form{max-height:35vh;overflow:auto;padding-top:8px;line-height:1.8}.chapter-revision fieldset{display:flex;gap:12px;flex-wrap:wrap;border:0;padding:6px 0}.chapter-revision fieldset label{display:flex;align-items:center;gap:5px}.chapter-revision textarea{display:block;width:100%;min-height:80px;border:1px solid #dce2d5;padding:8px;margin:6px 0;color:#334155}button:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid #65783e;outline-offset:2px}
</style>
