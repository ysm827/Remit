<script setup lang="ts">
import OverlayDetails from "@/pages/team/OverlayDetails.vue";
import type { PaperProposal } from "@/apis/teamApi";
defineProps<{
	proposal: PaperProposal;
	disabled?: boolean;
	processing?: boolean;
}>();
const emit = defineEmits<{ decide: [accept: boolean] }>();
</script>
<template>
<section class="review-card" aria-label="论文修改建议"><header><strong>{{ proposal.name }}</strong><span>{{ proposal.status === 'pending' ? '待审阅' : proposal.status === 'accepted' ? '已接受' : '已拒绝' }}</span></header><p>{{ proposal.summary }}</p><OverlayDetails title="源码差异"><template #trigger>源码差异</template><pre class="source-diff"><span v-for="(line,index) in proposal.diff.split('\n')" :key="index" :class="{added:line.startsWith('+'),removed:line.startsWith('-')}">{{ line }}{{ '\n' }}</span></pre></OverlayDetails><div v-if="proposal.status === 'pending'" class="review-actions"><button :disabled="disabled" @click="emit('decide',false)">拒绝</button><button class="primary-button" :disabled="disabled" @click="emit('decide',true)">{{ processing ? '处理中…' : '接受并编译' }}</button></div></section>
</template>
<style scoped>
.review-card{flex-shrink:0;border:1px solid #d9e1cd;background:#fafcf5;padding:12px;margin:8px 16px;font-size:12px;max-height:40vh;overflow:auto}.review-card header,.review-actions{display:flex;justify-content:space-between;gap:12px}.review-card p{margin:8px 0}.source-diff{max-height:24vh;overflow:auto;white-space:pre-wrap;background:#fff;padding:10px}.added{color:#245e27}.removed{color:#963333}.review-actions{justify-content:flex-end;margin-top:10px}.review-actions button{padding:6px 10px;border:1px solid #cdd5c1;border-radius:4px}.primary-button{background:#deff40;color:#202020}.review-actions button:disabled{opacity:.5}.review-actions button:focus-visible{outline:2px solid #65783e;outline-offset:2px}
</style>
