<script setup lang="ts">
import request from "@/utils/request";
import { ref, watch } from "vue";
import { Activity, FileSearch, Settings2, X, LoaderCircle, ChevronRight } from "lucide-vue-next";
import { PopoverRoot, PopoverAnchor, PopoverPortal, PopoverContent } from "reka-ui";

const props = defineProps<{ taskId?: string; open?: boolean; anchor?: HTMLElement; placement?: "top" | "bottom" }>();
const emit = defineEmits<{ settings: []; "update:open": [value: boolean] }>();
const interactedOutside = ref(false);
watch(() => props.open, value => { if (value) interactedOutside.value = false; });
function onInteractOutside(event: CustomEvent) {
 const target = event.detail.originalEvent.target;
 if (target instanceof Element && target.closest("[data-runtime-trigger]")) {
  event.preventDefault();
  return;
 }
 interactedOutside.value = true;
}
function restoreFocus(event: Event) {
 event.preventDefault();
 if (!interactedOutside.value) props.anchor?.focus();
}
function openSettings() {
 interactedOutside.value = true;
 emit("update:open", false);
 emit("settings");
}
const busy = ref(false);
const error = ref("");
const result = ref<{
	ready: boolean;
	scope: string;
	elapsed_seconds: number;
	checks: { id: string; label: string; required: boolean; status: string; detail?: string }[];
	runtime: { version: string; launch_mode: string; executor: string; data_directory: string };
} | null>(null);
const preview = ref("");
const exporting = ref(false);
const statusLabels: Record<string, string> = { passed: "通过", failed: "未通过", missing: "未安装" };

async function check() {
	if (busy.value) return;
	busy.value = true;
	error.value = "";
	try {
		result.value = (await request.post("/api/runtime/check", {}, { timeout: 120000 })).data;
	} catch {
		error.value = "本地自检未完成，请确认后端已启动；检查正在运行时请等待后重试。";
	} finally {
		busy.value = false;
	}
}
async function showPreview() {
	error.value = "";
	try {
		preview.value = JSON.stringify((await request.get("/api/diagnostics", { params: { task_id: props.taskId } })).data, null, 2);
	} catch {
		error.value = "诊断预览读取失败；请重启本地服务后再试。";
	}
}
function download() {
	if (!preview.value || exporting.value) return;
	exporting.value = true;
	// 下载用户看过的同一份快照，避免预览与实际导出内容发生变化。
	const url = URL.createObjectURL(new Blob([preview.value], { type: "application/json" }));
	const link = document.createElement("a");
	link.href = url;
	link.download = "remit-diagnostics.json";
	link.click();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
	exporting.value = false;
}
</script>

<template>
 <PopoverRoot :open="!!open" @update:open="emit('update:open', $event)">
  <PopoverAnchor :reference="anchor" as="span" class="runtime-anchor" />
  <PopoverPortal>
   <PopoverContent class="runtime-popover" :side="placement || 'bottom'" :align="placement === 'top' ? 'start' : 'end'" :side-offset="8" :collision-padding="12" aria-label="环境与诊断" @interact-outside="onInteractOutside" @close-auto-focus="restoreFocus">
    <header class="runtime-heading"><h2>环境与诊断</h2><button class="runtime-close" aria-label="关闭环境与诊断" @click="emit('update:open', false)"><X :size="16" /></button></header>
    <div class="runtime-actions">
     <button class="runtime-action" @click="openSettings"><Settings2 :size="18" /><span><strong>模型连接</strong><small>配置模型、密钥和接入方式</small></span><ChevronRight :size="15" /></button>
     <button class="runtime-action" aria-label="运行本地自检案例" :disabled="busy" @click="check"><LoaderCircle v-if="busy" :size="18" class="runtime-spin" /><Activity v-else :size="18" /><span><strong>{{ busy ? '正在检查本地环境…' : '本地自检' }}</strong><small>检查计算内核、图表和论文工具</small></span><ChevronRight v-if="!busy" :size="15" /></button>
     <button class="runtime-action" @click="showPreview"><FileSearch :size="18" /><span><strong>诊断信息</strong><small>预览并导出脱敏后的本地记录</small></span><ChevronRight :size="15" /></button>
    </div>
    <p class="runtime-note">自检仅运行本地固定案例，不调用模型。</p>
    <p v-if="error" role="alert" class="runtime-error">{{ error }}</p>
    <div v-if="result" role="status" class="check-results">
     <strong>{{ result.ready ? '本地计算检查通过' : '本地计算仍有阻断项' }} · {{ result.elapsed_seconds }} 秒</strong>
     <ul><li v-for="item in result.checks" :key="item.id"><span>{{ item.label }} <small>{{ item.required ? '必需' : '论文工具' }}</small></span><b :class="{ warning: item.status !== 'passed' }">{{ statusLabels[item.status] || item.status }}</b><p v-if="item.detail">{{ item.detail }}</p></li></ul>
     <p>{{ result.scope }}</p><p>版本 {{ result.runtime.version }} · {{ result.runtime.launch_mode === 'source' ? '源码启动' : '安装包启动' }} · 默认执行器 {{ result.runtime.executor }}</p><p class="data-path">数据目录：{{ result.runtime.data_directory }}</p>
    </div>
    <div v-if="preview" class="diagnostic-preview"><h3>诊断预览</h3><p>仅含环境与状态摘要，不含聊天、附件、密钥或模型地址。保存在本机，不自动上传。</p><pre tabindex="0">{{ preview }}</pre><button @click="download" :disabled="exporting">下载这份诊断</button></div>
   </PopoverContent>
  </PopoverPortal>
 </PopoverRoot>
</template>

<style scoped>
.runtime-anchor{display:none}
:global(.runtime-popover){z-index:80;width:360px;max-width:calc(100vw - 24px);max-height:min(70dvh,var(--reka-popover-content-available-height));overflow:auto;overscroll-behavior:contain;padding:14px;background:#fff;border:1px solid #e4e8de;border-radius:14px;box-shadow:0 12px 36px #00000014,0 2px 6px #00000006;color:#485142;font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
.runtime-heading{display:flex;align-items:center;justify-content:space-between;padding:0 2px 10px}
.runtime-heading h2{font-size:13px;font-weight:600;color:#333}
.runtime-close{display:grid;place-items:center;width:26px;height:26px;border-radius:6px;color:#737373}
.runtime-close:hover{background:#f3f3f3}
.runtime-actions{display:flex;flex-direction:column;gap:3px}
.runtime-action{display:flex;align-items:center;gap:12px;text-align:left;padding:11px 9px;border-radius:8px;width:100%;color:#626262}
.runtime-action:hover:not(:disabled){background:#f5f6f3}
.runtime-action>span{flex:1;min-width:0}
.runtime-action strong{display:block;font-size:13px;font-weight:500;color:#333}
.runtime-action small{display:block;font-size:11px;color:#808578;margin-top:2px}
.runtime-action>svg{flex-shrink:0}
.runtime-note{border-top:1px solid #e9ece5;margin-top:10px;padding:12px 8px 0;font-size:11px;color:#808578}
button:focus-visible,pre:focus-visible{outline:2px solid #65783e;outline-offset:2px}
button:disabled{opacity:.6;cursor:wait}
.check-results,.diagnostic-preview{margin-top:14px;border-top:1px solid #e4e8de;padding:14px 4px 0;font-size:12px;overflow-wrap:anywhere}
.check-results li{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;border-bottom:1px solid #e4e8de;padding:8px 0}
.check-results li p{width:100%;margin:0}
.check-results small{color:#697361;margin-left:6px}
.check-results>p,.diagnostic-preview>p{margin:8px 0;color:#697361;font-size:11px}
.warning,.runtime-error{color:#975b21}
.runtime-error{padding:8px;font-size:12px}
.diagnostic-preview pre{max-height:170px;overflow:auto;white-space:pre-wrap;background:#fafbf8;padding:10px;border:1px solid #e4e8de;border-radius:6px;font-size:11px}
.diagnostic-preview>button{border:1px solid #d9dfd0;border-radius:6px;background:white;padding:6px 10px;margin-top:10px}
.runtime-spin{animation:runtime-spin 1s linear infinite}
@keyframes runtime-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.runtime-spin{animation:none}}
</style>
