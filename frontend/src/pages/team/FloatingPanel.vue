<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "lucide-vue-next";
import { PopoverRoot, PopoverAnchor, PopoverPortal, PopoverContent, DialogRoot, DialogPortal, DialogContent, DialogTitle } from "reka-ui";
const props = withDefaults(defineProps<{ open: boolean; title: string; id?: string; anchor?: HTMLElement | null; width?: number; side?: "top" | "bottom" }>(), { width: 380, side: "top" });
const emit = defineEmits<{ "update:open": [open: boolean] }>();
const previousFocus = ref<HTMLElement>();
const clickedOutside = ref(false);
watch(() => props.open, open => { if (open) { clickedOutside.value = false; if (document.activeElement instanceof HTMLElement) previousFocus.value = document.activeElement; } });
function close() { emit("update:open", false); }
function restoreFocus(event: Event) {
 if (clickedOutside.value) { event.preventDefault(); return; }
 if (props.anchor || previousFocus.value?.isConnected) {
  event.preventDefault();
  (props.anchor || previousFocus.value)?.focus();
 }
}
function outside(event: CustomEvent) {
 const target = event.detail.originalEvent.target;
 if (target instanceof Node && props.anchor?.contains(target)) event.preventDefault();
 else clickedOutside.value = true;
}
</script>
<template>
 <PopoverRoot v-if="anchor" :open="open" @update:open="emit('update:open', $event)">
  <PopoverAnchor :reference="anchor" as="span" style="display:none" />
  <PopoverPortal><PopoverContent :id="id" class="remit-floating-panel" :style="{ width: `${width}px` }" :side="side" align="end" :side-offset="8" :collision-padding="12" :aria-label="title" @interact-outside="outside" @close-auto-focus="restoreFocus">
   <header class="floating-heading"><h2>{{ title }}</h2><button :aria-label="`关闭${title}`" @click="close"><X :size="16" /></button></header>
   <div class="floating-body"><slot /></div>
  </PopoverContent></PopoverPortal>
 </PopoverRoot>
 <DialogRoot v-else :open="open" :modal="false" @update:open="emit('update:open', $event)">
  <DialogPortal><DialogContent :id="id" class="remit-floating-panel floating-reader" :style="{ width: `${width}px` }" :aria-describedby="undefined" @close-auto-focus="restoreFocus" @interact-outside="outside">
   <header class="floating-heading"><DialogTitle>{{ title }}</DialogTitle><button :aria-label="`关闭${title}`" @click="close"><X :size="16" /></button></header>
   <div class="floating-body"><slot /></div>
  </DialogContent></DialogPortal>
 </DialogRoot>
</template>
<style>
.remit-floating-panel{z-index:90;max-width:calc(100vw - 24px);max-height:min(600px,80dvh);display:flex;flex-direction:column;overflow:hidden;background:#fff;border:1px solid #e5e5e5;border-radius:16px;box-shadow:0 12px 40px #0000001a,0 2px 8px #00000008;color:#30332d;font:13px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;outline:none}
.remit-floating-panel[data-side]{max-height:min(560px,80dvh,var(--reka-popover-content-available-height))}
.floating-reader{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%)}
.floating-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px 8px;flex-shrink:0}
.floating-heading h2{margin:0;font-size:13px;font-weight:600}
.floating-heading button{display:grid;place-items:center;width:26px;height:26px;flex-shrink:0;border-radius:7px;color:#777}
.floating-heading button:hover{background:#f1f1f1}
.floating-body{padding:4px 16px 16px;overflow:auto;min-height:0;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#d8d8d8 transparent;overflow-wrap:anywhere}
.floating-body pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:#f7f7f7;border-radius:8px;font:12px/1.7 Consolas,monospace;max-height:none}
.floating-body textarea{display:block;width:100%;min-height:74px;max-height:180px;resize:vertical;border:1px solid #e3e3e3;border-radius:8px;padding:9px;font:inherit;background:#fafafa}
.floating-body button:focus-visible,.floating-heading button:focus-visible{outline:2px solid #777;outline-offset:2px}
.floating-body .detail-section{padding:12px 0;border-bottom:1px solid #eee}
.floating-body .detail-section h3{font-size:13px;font-weight:600;margin:0 0 8px}
</style>
