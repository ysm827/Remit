<script setup lang="ts">
import { computed } from "vue";
import { Check, ChevronDown } from "lucide-vue-next";
import {
 DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal,
 DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup,
 DropdownMenuRadioItem, DropdownMenuItemIndicator,
} from "reka-ui";

const props = defineProps<{
 modelValue: string;
 label: string;
 title: string;
 disabled?: boolean;
 options: { value: string; label: string; description?: string }[];
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const selected = computed(() => props.options.find(option => option.value === props.modelValue));
</script>

<template>
 <DropdownMenuRoot :modal="false">
  <DropdownMenuTrigger class="composer-select-trigger" :aria-label="label" :disabled="disabled || !options.length">
   <span>{{ selected?.label || title }}</span><ChevronDown :size="13" aria-hidden="true" />
  </DropdownMenuTrigger>
  <DropdownMenuPortal>
   <DropdownMenuContent class="composer-select-menu" side="top" align="end" :side-offset="8" :collision-padding="12" :aria-label="title">
    <DropdownMenuLabel class="composer-select-title">{{ title }}</DropdownMenuLabel>
    <DropdownMenuRadioGroup :model-value="modelValue" @update:model-value="typeof $event === 'string' && emit('update:modelValue', $event)">
     <DropdownMenuRadioItem v-for="option in options" :key="option.value" :value="option.value" :text-value="option.label" class="composer-select-option">
      <span class="composer-select-copy"><span>{{ option.label }}</span><small v-if="option.description">{{ option.description }}</small></span>
      <span class="composer-select-check"><DropdownMenuItemIndicator><Check :size="15" /></DropdownMenuItemIndicator></span>
     </DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
   </DropdownMenuContent>
  </DropdownMenuPortal>
 </DropdownMenuRoot>
</template>

<style>
.composer-select-trigger{display:inline-flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;max-width:175px;padding:6px 8px;border-radius:7px;background:transparent;color:#626262;font-size:12px;text-align:left;cursor:pointer}
.composer-select-trigger>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.composer-select-trigger svg{flex-shrink:0;color:#818181}
.composer-select-trigger:hover,.composer-select-trigger[data-state=open]{background:#e8e8e8;color:#202020}
.composer-select-trigger:focus-visible{outline:2px solid #777;outline-offset:2px}
.composer-select-menu{z-index:110;width:272px;max-width:calc(100vw - 24px);max-height:min(300px,var(--reka-dropdown-menu-content-available-height));overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#d8d8d8 transparent;padding:6px;background:#fff;border:1px solid #e5e5e5;border-radius:14px;box-shadow:0 10px 32px #00000014,0 2px 6px #00000006;color:#252525;font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;outline:none}
.composer-select-title{padding:7px 10px 8px;color:#848484;font-size:11px;font-weight:500}
.composer-select-option{display:flex;align-items:center;gap:12px;padding:9px 10px;border-radius:8px;outline:none;cursor:pointer;user-select:none}
.composer-select-option[data-highlighted]{background:#f2f2f2}
.composer-select-copy{display:flex;flex:1;flex-direction:column;gap:2px;min-width:0}
.composer-select-copy small{font-size:11px;color:#858585}
.composer-select-check{display:flex;width:16px;flex-shrink:0;color:#4d573b}
@media(max-width:600px){.composer-select-trigger{max-width:114px;padding:5px 4px;gap:5px;font-size:11px}}
</style>
