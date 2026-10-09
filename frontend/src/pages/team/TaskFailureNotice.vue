<script setup lang="ts">
import type { TeamState } from "@/apis/teamApi";
import ExecutionBudgetRecovery from "./ExecutionBudgetRecovery.vue";
import ModelBudgetRecovery from "./ModelBudgetRecovery.vue";
defineProps<{ state: TeamState; sending: boolean }>();
const emit = defineEmits<{ resume: []; resumed: []; settings: []; view: [value: string] }>();
</script>
<template>
  <div v-if="state.status === 'failed' || (state.status === 'stopped' && state.failure)" class="failure-notice" role="alert">
    <p v-if="['MODEL_STAGE_BUDGET','EXECUTION_BUDGET'].includes(state.failure?.code || '')">额度暂停 · 成果已保留</p>
    <p>{{ state.failure?.reason || '当前步骤未完成，文件和进度已保留。' }}</p>
    <ExecutionBudgetRecovery v-if="state.failure?.code === 'EXECUTION_BUDGET'" :task-id="state.task_id" :node-id="state.current_node" :sending="sending" @resumed="emit('resumed')" />
    <ModelBudgetRecovery v-if="state.failure?.code === 'MODEL_STAGE_BUDGET'" :task-id="state.task_id" :node-id="state.current_node" :sending="sending" @resumed="emit('resumed')" />
    <div class="failure-actions">
      <button v-if="!state.failure?.retrying && !['EXECUTION_BUDGET','MODEL_STAGE_BUDGET'].includes(state.failure?.code || '')" :disabled="sending" @click="emit('resume')">重试当前步骤</button>
      <button v-if="!state.failure?.code.startsWith('EXECUTION_BUDGET') && state.failure?.code !== 'MODEL_STAGE_BUDGET'" @click="emit('settings')">修改模型配置</button>
      <button @click="emit('view', 'files')">查看已保存成果</button>
    </div>
  </div>
</template>
<style scoped>
.failure-notice{font-size:12px;line-height:1.6;padding:8px 0;color:var(--muted-foreground)}.failure-notice p{margin:0 0 6px}.failure-actions{display:flex;flex-wrap:wrap;gap:12px}.failure-actions button{text-decoration:underline;text-underline-offset:3px}.failure-actions button:disabled{opacity:.5}.failure-actions button:focus-visible{outline:2px solid currentColor;outline-offset:3px}
</style>
