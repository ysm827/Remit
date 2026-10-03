<script setup lang="ts">
import request from "@/utils/request";
import { ref } from "vue";

const props = defineProps<{ taskId?: string }>();
const emit = defineEmits<{ settings: [] }>();
const open = ref(false);
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
	<section class="runtime-panel" aria-label="环境自检与诊断">
		<button class="runtime-toggle" :aria-expanded="open" @click="open = !open">
			<span>{{ taskId ? '本地环境与失败诊断' : '第一次使用？先检查环境，再配置模型' }}</span><span>{{ open ? '收起 −' : '展开 +' }}</span>
		</button>
		<div v-if="open" class="runtime-body">
			<ol v-if="!taskId" class="setup-steps"><li>检查本地环境</li><li>保存模型连接</li><li>授权能力验证</li><li>导入问题并确认方案</li></ol>
			<p>环境检查运行固定代码与固定数据，不调用模型，也不收取模型费用。实际解题需要你自己的模型服务。</p>
			<div class="runtime-actions"><button :disabled="busy" @click="check">{{ busy ? '正在检查内核、图表和论文工具…' : '运行本地自检案例' }}</button><button @click="emit('settings')">配置模型</button><button @click="showPreview">预览脱敏诊断</button></div>
			<p v-if="error" role="alert">{{ error }}</p>
			<div v-if="result" role="status" class="check-results">
				<strong>{{ result.ready ? '本地计算检查通过' : '本地计算仍有阻断项' }} · {{ result.elapsed_seconds }} 秒</strong>
				<ul><li v-for="item in result.checks" :key="item.id"><span>{{ item.label }} <small>{{ item.required ? '必需' : '论文工具' }}</small></span><b :class="{ warning: item.status !== 'passed' }">{{ statusLabels[item.status] || item.status }}</b><p v-if="item.detail">{{ item.detail }}</p></li></ul>
				<p>{{ result.scope }}</p><p>版本 {{ result.runtime.version }} · {{ result.runtime.launch_mode === 'source' ? '源码启动' : '安装包启动' }} · 默认执行器 {{ result.runtime.executor }}</p><p class="data-path">数据目录：{{ result.runtime.data_directory }}</p>
			</div>
			<div v-if="preview" class="diagnostic-preview"><h3>将导出的完整内容</h3><p>只包含环境、状态和元数据摘要；不含模型地址、原始错误、聊天、代码、附件或论文。保存在本机，不自动上传。</p><pre tabindex="0">{{ preview }}</pre><button @click="download" :disabled="exporting">下载这份诊断</button></div>
		</div>
	</section>
</template>

<style scoped>
.runtime-panel{border:1px solid #e4e8de;border-radius:10px;margin:12px 24px;background:#fafbf8;font-size:12px;color:#485142}.runtime-toggle{display:flex;justify-content:space-between;gap:16px;text-align:left;width:100%;padding:12px 16px}.runtime-body{padding:0 16px 16px;max-height:55vh;overflow:auto;line-height:1.7}.runtime-body p{margin:8px 0}.setup-steps{display:flex;gap:24px;flex-wrap:wrap;padding-left:16px;list-style:decimal}.runtime-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}button{border-radius:6px}button:focus-visible,pre:focus-visible{outline:2px solid #65783e;outline-offset:2px}.runtime-actions button,.diagnostic-preview>button{border:1px solid #d9dfd0;background:white;padding:6px 10px}button:disabled{opacity:.6;cursor:wait}.check-results li{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;border-top:1px solid #e4e8de;padding:8px 0}.check-results li p{width:100%;margin:0}.check-results small{color:#697361;margin-left:6px}.warning,[role=alert]{color:#975b21}.data-path{overflow-wrap:anywhere}.diagnostic-preview pre{max-height:200px;overflow:auto;background:white;padding:10px;border:1px solid #e4e8de;font-size:11px}@media(max-width:640px){.runtime-panel{margin:8px 12px}.setup-steps{gap:8px 24px}}
</style>
