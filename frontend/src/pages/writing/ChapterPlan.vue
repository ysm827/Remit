<script setup lang="ts">
import FloatingPanel from "@/pages/team/FloatingPanel.vue";
import OverlayDetails from "@/pages/team/OverlayDetails.vue";
import request from "@/utils/request";
import { ref, watch } from "vue";
const props = defineProps<{ taskId: string }>();
const open = ref(false);
const busy = ref(false);
const notes = ref("");
const error = ref("");
const saved = ref(false);
let revision = 0;
const plan = ref<{ version: string; evidence_revision: string; notes: string; sections: { key: string; question: string; model: unknown; evidence_files: string[]; figures: string[]; limitations: unknown }[] } | null>(null);
watch(() => props.taskId, () => { revision++; plan.value = null; notes.value = ""; open.value = false; busy.value = false; error.value = ""; saved.value = false; });
async function load() {
	open.value = !open.value;
	if (!open.value || plan.value || busy.value) return;
	const current = revision;
	busy.value = true;
	try { const response = await request.get(`/api/writing/${encodeURIComponent(props.taskId)}/chapter-plan`); if (current !== revision) return; plan.value = response.data; notes.value = plan.value?.notes || ""; error.value = ""; }
	catch { if (current === revision) error.value = "章节计划读取失败，请重试。"; }
	finally { if (current === revision) busy.value = false; }
}
async function save() {
	if (!plan.value || busy.value) return;
	busy.value = true;
	const current = revision;
	saved.value = false;
	try { const response = await request.put(`/api/writing/${encodeURIComponent(props.taskId)}/chapter-plan`, { notes: notes.value, version: plan.value.version, evidence_revision: plan.value.evidence_revision }); if (current !== revision) return; plan.value = response.data; saved.value = true; error.value = ""; }
	catch { if (current === revision) error.value = "未保存：计划或证据可能已更新，或正在写作。本地修改仍保留，请重新核对。"; }
	finally { if (current === revision) busy.value = false; }
}
</script>
<template>
	<section class="chapter-plan"><button :aria-expanded="open" @click="load">{{ open ? '收起章节计划' : '查看与修改章节计划' }}</button><FloatingPanel v-model:open="open" title="章节计划" :width="580"><div class="plan-body"><p>计划来自当前计算证据。可修改论证顺序、图表用途和解释重点；新增科学结论需要先完成相应实验。</p><p v-if="error" role="alert">{{ error }}</p><p v-if="!plan?.sections?.length">同步建模成果后，逐问计划会显示在这里。</p><OverlayDetails :title="section.key + ' · ' + section.question" v-for="section in plan?.sections" :key="section.key"><template #trigger>{{ section.key }} · {{ section.question }}</template><p>模型：{{ section.model }}</p><p>证据：{{ section.evidence_files.join('、') || '尚无文件' }}</p><p>图表：{{ section.figures.join('、') || '尚无图表' }}</p><p>局限：{{ section.limitations }}</p></OverlayDetails><template v-if="plan?.evidence_revision"><label>组织与修订意见<textarea v-model="notes" maxlength="10000" aria-label="章节计划修改意见" /></label><button :disabled="busy" @click="save">{{ busy ? '处理中…' : '保存计划意见' }}</button><span v-if="saved" role="status">已保存，下次写作使用新计划。</span></template></div></FloatingPanel></section>
</template>
<style scoped>
.chapter-plan{padding:8px 18px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#536248}.chapter-plan button{border:1px solid #dce2d5;border-radius:5px;padding:5px 9px;background:#fafbf8}.plan-body{line-height:1.8;padding:8px 0}.plan-body details{padding:6px 0}.plan-body summary{cursor:pointer}.plan-body textarea{display:block;width:100%;min-height:80px;border:1px solid #dce2d5;padding:8px;color:#334155;margin:6px 0}.plan-body [role=alert]{color:#a04d24}button:focus-visible,textarea:focus-visible{outline:2px solid #65783e;outline-offset:2px}
</style>
