<script setup lang="ts">
import { ref } from "vue";
import { ChevronRight } from "lucide-vue-next";
import FloatingPanel from "./FloatingPanel.vue";
withDefaults(defineProps<{ title?: string; width?: number }>(), { title: "详细内容", width: 620 });
const open = ref(false);
</script>
<template>
 <div class="overlay-details">
  <button class="overlay-details-trigger" :aria-expanded="open" aria-haspopup="dialog" @click="open = true"><slot name="trigger">查看详情</slot><ChevronRight :size="14" /></button>
  <FloatingPanel v-model:open="open" :title="title" :width="width"><slot /></FloatingPanel>
 </div>
</template>
<style scoped>
.overlay-details-trigger{display:flex;align-items:center;gap:7px;width:100%;padding:7px 0;text-align:left;font-size:12px;color:#686868;border-radius:6px}
.overlay-details-trigger:hover{color:#202020;background:#f6f6f6}.overlay-details-trigger:focus-visible{outline:2px solid #777;outline-offset:2px}.overlay-details-trigger svg{flex-shrink:0;margin-left:auto}
</style>
