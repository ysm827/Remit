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
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
const visible = computed(() =>
	files.value.filter((file) =>
		file.filename.toLowerCase().includes(filter.value.toLowerCase()),
	),
);
async function refresh() {
	try {
		const [list, detail] = await Promise.all([
			getFiles(props.task_id),
			request.get(
				`/api/projects/${encodeURIComponent(props.task_id)}/artifacts`,
			),
		]);
		const entries = await Promise.all(
			list.data
				.filter((file) => !/\.(ttf|otf|ttc)$/i.test(file.filename))
				.map(async (file) => ({
					filename: file.filename,
					url:
						file.download_url ||
						(await getFileDownloadUrl(props.task_id, file.filename)).data
							.download_url,
				})),
		);
		if (!disposed) {
			files.value = entries;
			artifacts.value = detail.data;
			error.value = "";
		}
	} catch (cause) {
		if (!disposed) error.value = explainModelingSubmissionFailure(cause);
	} finally {
		if (!disposed) loading.value = false;
	}
}
watch(
	() => props.sequence,
	() => {
		clearTimeout(timer);
		timer = setTimeout(() => void refresh(), 1200);
	},
);
onMounted(refresh);
onBeforeUnmount(() => {
	disposed = true;
	clearTimeout(timer);
});
</script>
<template>
 <section class="project-files" aria-label="项目文件与结果">
  <header><h1>文件与结果</h1><button @click="refresh" aria-label="刷新项目成果"><RefreshCw :size="16" /></button></header>
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
</style>
