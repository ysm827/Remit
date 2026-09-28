<script setup lang="ts">
import { getFileDownloadUrl, getFiles } from "@/apis/filesApi";
import { explainModelingSubmissionFailure } from "@/apis/submitModelingApi";
import request from "@/utils/request";
import { FileText, RefreshCw, Search } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from "vue";
import ArtifactContent from "./ArtifactContent.vue";
import ResultReport from "./ResultReport.vue";
import { artifactLabel } from "./artifactLabels";
const props = defineProps<{ task_id: string; sequence: number }>();
const files = ref<{ filename: string; url: string }[]>([]);
const artifacts = ref<{
	problem?: { ques_all?: string };
	model?: unknown;
	results?: Record<string, unknown>;
	data?: unknown;
}>({});
provide("artifactMarkdownContext", () => ({
	taskId: props.task_id,
	imageUrls: Object.fromEntries(
		files.value.map((file) => [
			file.filename.replace(/\.svg\.png$/i, ".svg"),
			file.url,
		]),
	),
}));
const filter = ref("");
const error = ref("");
const loading = ref(true);
const refreshing = ref(false);
const refreshedAt = ref("");
const refreshNotice = ref("");
let queued = false;
let revision = 0;
let lastContent = "";
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
const visible = computed(() =>
	files.value.filter((file) =>
		file.filename.toLowerCase().includes(filter.value.toLowerCase()),
	),
);
async function refresh(manual = false) {
	if (refreshing.value) { queued = true; return; }
	const taskId = props.task_id;
	const currentRevision = revision;
	refreshing.value = true;
	if (manual) refreshNotice.value = "Remit 正在核对最新文件与结果…";
	try {
		const [list, detail] = await Promise.all([
			getFiles(taskId),
			request.get(
				`/api/projects/${encodeURIComponent(taskId)}/artifacts`,
			),
		]);
		const entries = await Promise.all(
			list.data
				.filter((file) => !/\.(ttf|otf|ttc)$/i.test(file.filename))
				.map(async (file) => ({
					filename: file.filename,
					url:
						file.download_url ||
						(await getFileDownloadUrl(taskId, file.filename)).data
							.download_url,
				})),
		);
		if (!disposed && currentRevision === revision) {
			const content = JSON.stringify([list.data.map(file => [file.filename, file.size, file.modified_time]).sort((a, b) => String(a[0]).localeCompare(String(b[0]))), detail.data]);
			if (manual) refreshNotice.value = content === lastContent
				? "已核对，文件列表与成果摘要暂无变化。"
				: "新内容已同步，来看看这次的成果吧。";
			lastContent = content;
			refreshedAt.value = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
			files.value = entries;
			artifacts.value = detail.data;
			error.value = "";
		}
	} catch (cause) {
		if (!disposed && currentRevision === revision) {
			error.value = "这次同步没成功：" + explainModelingSubmissionFailure(cause);
			refreshNotice.value = "已保留上次读取的内容，可以再试一次。";
		}
	} finally {
		if (!disposed) {
			refreshing.value = false;
			if (currentRevision === revision) loading.value = false;
			if (queued) { queued = false; void refresh(); }
		}
	}
}
watch(
	() => props.sequence,
	() => {
		clearTimeout(timer);
		timer = setTimeout(() => void refresh(), 1200);
	},
);
watch(() => props.task_id, () => {
	revision++;
	files.value = [];
	artifacts.value = {};
	lastContent = "";
	refreshedAt.value = "";
	refreshNotice.value = "";
	error.value = "";
	loading.value = true;
	clearTimeout(timer);
	void refresh();
});
onMounted(() => void refresh());
onBeforeUnmount(() => {
	disposed = true;
	clearTimeout(timer);
});
</script>
<template>
 <section class="project-files" aria-label="项目文件与结果">
  <header><div><h1>小队成果架</h1><p class="shelf-caption">赛题、模型与计算证据，都替你收在这里。</p></div><button class="refresh-button" type="button" @click="refresh(true)" :disabled="refreshing" :aria-busy="refreshing" aria-label="刷新项目成果"><RefreshCw :size="16" :class="{ spinning: refreshing }" aria-hidden="true" />{{ refreshing ? '正在同步…' : '刷新成果' }}</button></header>
  <div class="sync-status" role="status" aria-live="polite"><span>{{ refreshNotice || '成果会自动同步，也可以随时手动核对。' }}</span><time v-if="refreshedAt">上次同步 {{ refreshedAt }}</time></div>
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-if="loading" class="empty" role="status">正在读取项目内容…</p>
  <template v-else>
   <details open class="artifact-section"><summary>赛题原文</summary><div class="section-body"><ArtifactContent :value="artifacts.problem?.ques_all || '尚未保存题面'" /></div></details>
   <details v-if="artifacts.model && Object.keys(artifacts.model).length" open class="artifact-section"><summary>模型方案</summary><div class="section-body"><ArtifactContent :value="artifacts.model" /></div></details>
   <details v-for="(result,key) in artifacts.results" :key="key" open class="artifact-section"><summary>{{ artifactLabel(String(key)) }} · 计算结果</summary><div class="section-body"><ResultReport :result="result" :files="files" /></div></details>
  </template>
  <div class="file-heading"><h2>项目文件 <small>{{ files.length }}</small></h2><label><Search :size="14" /><input v-model="filter" aria-label="搜索项目文件" placeholder="搜索文件" /></label></div>
  <a v-for="file in visible" :key="file.filename" :href="file.url" target="_blank" rel="noopener" class="file"><FileText :size="16" /><span>{{ file.filename }}</span><small>查看 / 下载 ↗</small></a>
  <p v-if="!visible.length" class="empty">{{ filter ? '没有匹配的文件' : '附件、代码、图表与结果将保存在这里。' }}</p>
 </section>
</template>
<style scoped>
.project-files{flex:1;min-width:0;overflow:auto;padding:28px 36px;color:#242424}.project-files>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:25px}.project-files h1{font-size:20px;font-weight:550}.project-files details{border-bottom:1px solid #e5e5e5;padding:12px 0}.project-files summary{cursor:pointer;font-size:13px}.section-body{padding:20px 4px 12px;max-width:1080px;min-width:0}.artifact-section>summary{font-weight:550;font-size:14px}.artifact-section>summary:focus-visible{outline:2px solid #666;outline-offset:4px}.project-files>header button:focus-visible{outline:2px solid #666;outline-offset:4px}.file-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:32px 0 14px}.file-heading h2{font-weight:550}.file-heading small{color:#888;margin-left:8px}.file-heading label{display:flex;align-items:center;gap:8px;color:#888}.file-heading input{font-size:12px;outline:none;max-width:150px;border-bottom:1px solid #ddd;padding:5px;background:transparent}.file{display:flex;align-items:center;gap:12px;padding:14px 5px;border-bottom:1px solid #ededed;font-size:12px}.file:hover{background:#fafafa}.file>span{flex:1;overflow-wrap:anywhere;min-width:0}.file small{color:#777;white-space:nowrap}.empty{color:#888;padding:30px 0;font-size:12px}@media(max-width:760px){.project-files{padding:22px 18px}.file-heading label input{max-width:90px}}
.shelf-caption{font-size:12px;color:#737373;margin-top:5px}.refresh-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:36px;padding:7px 12px;border:1px solid #ddd;border-radius:9px;font-size:12px;white-space:nowrap}.refresh-button:hover:not(:disabled){background:#f8faf3}.refresh-button:disabled{opacity:.65;cursor:wait}.sync-status{display:flex;flex-wrap:wrap;gap:6px 16px;justify-content:space-between;color:#666;font-size:12px;min-height:28px;margin-bottom:12px}.sync-status time{font-size:11px}.spinning{animation:refresh-spin 1s linear infinite}@keyframes refresh-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}@media(max-width:520px){.project-files>header{gap:12px;align-items:flex-start}.shelf-caption{max-width:180px}}
</style>
