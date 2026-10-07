<script setup lang="ts">
import OverlayDetails from "@/pages/team/OverlayDetails.vue";
import { getFileDownloadUrl, getFiles } from "@/apis/filesApi";
import { explainModelingSubmissionFailure } from "@/apis/submitModelingApi";
import request from "@/utils/request";
import { ArrowLeft, ArrowUpRight, CircleHelp, FileText, RefreshCw, Search } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from "vue";
import ArtifactContent from "./ArtifactContent.vue";
import ResultReport from "./ResultReport.vue";
import { artifactLabel, asRecord } from "./artifactLabels";
import { resultOverview } from "./resultOverview";
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
type Page = "overview" | "results" | "materials" | "files";
const page = ref<Page>("overview");
const selected = ref("");
const detailTab = ref<"conclusion" | "figures" | "checks" | "process" | "files">("conclusion");
const materialTab = ref("problem");
const filePage = ref(1);
const relatedPage = ref(1);
const fileKind = ref("all");
const cardPage = ref(1);
const rows = computed(() => Object.entries(artifacts.value.results || {}).map(([key, value]) => resultOverview(key, value)).sort((a,b) => a.key.localeCompare(b.key, undefined, { numeric: true })));
const questions = computed(() => rows.value.filter(r => /^ques(?:tion)?_?\d+$/i.test(r.key)));
const overviewRows = computed(() => questions.value.length ? questions.value : rows.value);
const cards = computed(() => overviewRows.value.slice((cardPage.value-1)*4,cardPage.value*4));
const cardPages = computed(() => Math.max(1, Math.ceil(overviewRows.value.length/4)));
const current = computed(() => rows.value.find(r => r.key === selected.value));
const attention = computed(() => rows.value.filter(r => r.tone === "attention"));
const reviewed = computed(() => rows.value.filter(r => r.tone === "reviewed").length);
const plans = computed(() => Object.entries(asRecord(asRecord(artifacts.value.model).questions_solution)));
function navigate(next: Page) { page.value = next; }
function openResult(key: string, tab: typeof detailTab.value = "conclusion") { relatedPage.value = 1; selected.value = key; detailTab.value = tab; page.value = "results"; }
function fileType(name: string) {
 if (/\.(png|jpe?g|svg|webp|gif)$/i.test(name)) return "figures";
 if (/\.(py|m|ipynb|r)$/i.test(name)) return "code";
 if (/\.(csv|xlsx?|json|mat)$/i.test(name)) return "data";
 return "documents";
}
const visible = computed(() => files.value.filter(file => file.filename.toLowerCase().includes(filter.value.toLowerCase()) && (fileKind.value === "all" || fileType(file.filename) === fileKind.value)));
const filePages = computed(() => Math.max(1,Math.ceil(visible.value.length/12)));
const fileSlice = computed(() => visible.value.slice((filePage.value-1)*12,filePage.value*12));
const relatedFiles = computed(() => files.value.filter(file => current.value?.related.includes(file.filename)));
watch([filter, fileKind], () => { filePage.value = 1; });
watch(filePages, value => { filePage.value = Math.min(filePage.value,value); });
watch(cardPages, value => { cardPage.value = Math.min(cardPage.value,value); });
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
			error.value = `这次同步没成功：${explainModelingSubmissionFailure(cause)}`;
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
	page.value = "overview"; selected.value = ""; detailTab.value = "conclusion";
	filter.value = ""; fileKind.value = "all"; filePage.value = 1; cardPage.value = 1; materialTab.value = "problem";
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
  <header class="shelf-header"><div><h1>小队成果架</h1><p class="shelf-caption">先看结果，再看依据。</p></div><button class="refresh-button" type="button" @click="refresh(true)" :disabled="refreshing" :aria-busy="refreshing" aria-label="刷新项目成果"><RefreshCw :size="15" :class="{ spinning: refreshing }" />{{ refreshing ? '正在同步…' : '刷新成果' }}</button></header>
  <nav class="shelf-nav" aria-label="成果导航"><button v-for="tab in [{id:'overview',label:'成果总览'},{id:'results',label:'分步成果'},{id:'materials',label:'题面与方案'},{id:'files',label:'全部文件'}]" :key="tab.id" :aria-current="page === tab.id ? 'page' : undefined" @click="navigate(tab.id as Page)">{{ tab.label }}</button><time v-if="refreshedAt">同步于 {{ refreshedAt }}</time></nav>
  <div class="sync-status" role="status" aria-live="polite">{{ refreshNotice }}</div>
  <p v-if="error" role="alert" class="sync-error">{{ error }}</p>
  <p v-if="loading" class="empty" role="status">正在读取项目成果…</p>
  <div v-else class="shelf-body" :key="page">
   <template v-if="page === 'overview'">
    <div class="overview-heading"><div><h2>{{ rows.length ? '这次做到了哪里' : '成果正在路上' }}</h2></div><span class="muted">报告复核状态，不代替你的验收</span></div>
    <div class="status-strip"><div><strong>{{ rows.length }}</strong><span>步骤有记录</span></div><div><strong>{{ reviewed }}</strong><span>复核通过</span></div><button @click="openResult(attention[0]?.key || rows[0]?.key || '', 'checks')"><strong :class="{warning:attention.length}">{{ attention.length }}</strong><span>步骤待核验 <ArrowUpRight :size="13" /></span></button><button @click="navigate('files')"><strong>{{ files.length }}</strong><span>文件已保存 <ArrowUpRight :size="13" /></span></button></div>
    <div v-if="attention.length" class="attention-note"><CircleHelp :size="18" /><div><strong>有结果，也有尚未确认的部分</strong><p>{{ attention.map(r=>r.title).join('、') }}仍需核验。查看依据后再决定如何使用。</p></div><button @click="openResult(attention[0].key,'checks')">查看待核验项 →</button></div>
    <div class="section-heading"><h2>各问主要结果</h2><button @click="navigate('results')">查看全部步骤 →</button></div>
    <div v-if="!rows.length" class="empty"><FileText :size="28" /><h3>还没有保存计算结果</h3><p>可以先查看题面与方案；产生结果后会自动出现在这里。</p><p class="problem-excerpt">{{ artifacts.problem?.ques_all?.slice(0, 240) }}</p><button @click="navigate('materials')">查看题面与方案 →</button></div>
    <div class="result-grid"><article v-for="row in cards" :key="row.key" class="result-card"><div class="card-heading"><h3>{{ row.title }}</h3><span class="badge" :class="row.tone">{{ row.status }}</span></div><p class="result-excerpt">{{ row.tone === 'attention' && row.warning ? row.warning : row.excerpt }}</p><dl v-if="row.metrics.length" class="metrics"><div v-for="m in row.metrics.slice(0,3)" :key="m.name"><dt>{{ m.name }}</dt><dd>{{ m.value }}</dd><small v-if="m.baseline !== undefined">基准 {{ m.baseline }}</small></div></dl><p v-else class="muted">尚无结构化指标，请查看结论原文。</p><button class="card-link" @click="openResult(row.key)">查看结论与依据 <ArrowUpRight :size="15" /></button></article></div>
    <div v-if="cardPages > 1" class="pagination"><button :disabled="cardPage===1" @click="cardPage--">上一页</button><span>{{cardPage}} / {{cardPages}}</span><button :disabled="cardPage===cardPages" @click="cardPage++">下一页</button></div>
    <div v-if="questions.length && rows.length > questions.length" class="supporting"><span class="muted">支撑工作</span><button v-for="row in rows.filter(r=>!questions.includes(r))" :key="row.key" @click="openResult(row.key)">{{row.title}} <span class="status-dot" :class="row.tone" /> <ArrowUpRight :size="13" /></button></div>
   </template>
   <div v-else-if="page === 'results'" class="detail-layout">
    <nav class="step-list" aria-label="选择结果步骤"><button v-for="row in rows" :key="row.key" :aria-current="selected === row.key ? 'page' : undefined" @click="openResult(row.key)"><span>{{row.title}}</span><small :class="{warning:row.tone==='attention'}">{{row.status}}</small></button><p v-if="!rows.length" class="empty">暂无步骤结果</p></nav>
    <main class="detail-content" v-if="current"><button class="back" @click="navigate('overview')"><ArrowLeft :size="14" /> 成果总览</button><div class="detail-title"><h2>{{ current.title }}</h2><span class="badge" :class="current.tone">{{current.status}}</span></div>
     <nav class="detail-nav" aria-label="结果详情导航"><button v-for="tab in [{id:'conclusion',label:'结论'},{id:'figures',label:'图表'},{id:'checks',label:'核验依据'},{id:'process',label:'计算过程'},{id:'files',label:'相关文件'}]" :key="tab.id" :aria-current="detailTab===tab.id ? 'page' : undefined" @click="detailTab=tab.id as typeof detailTab">{{tab.label}}</button></nav>
     <div class="detail-reader" :key="current.key + detailTab">
      <template v-if="detailTab==='conclusion'"><div v-if="current.tone==='attention'" class="attention-note"><CircleHelp :size="18" /><p>{{current.warning || '报告存在未通过或待人工核验的检查，请先查看核验依据。'}}</p><button @click="detailTab='checks'">查看依据 →</button></div><dl v-if="current.metrics.length" class="metrics detail-metrics"><div v-for="m in current.metrics" :key="m.name"><dt>{{m.name}}</dt><dd>{{m.value}}</dd><small v-if="m.baseline !== undefined">基准 {{m.baseline}}</small></div></dl><section v-if="current.method"><h3>采用的方法</h3><p>{{current.method}}</p></section><section v-if="current.activity"><h3>做了什么</h3><p>{{current.activity}}</p></section><section><h3>计算结论原文</h3><ArtifactContent :value="current.narrative || current.excerpt" /></section></template>
      <template v-else-if="detailTab==='files'"><p class="muted">仅显示本步骤明确登记的文件。</p><a v-for="file in relatedFiles.slice((relatedPage-1)*12,relatedPage*12)" :key="file.filename" :href="file.url" target="_blank" rel="noopener" class="file"><FileText :size="16" /><span>{{file.filename}}</span><small>查看 / 下载 ↗</small></a><div v-if="relatedFiles.length > 12" class="pagination"><button :disabled="relatedPage===1" @click="relatedPage--">上一页</button><span>{{relatedPage}} / {{Math.ceil(relatedFiles.length/12)}}</span><button :disabled="relatedPage>=Math.ceil(relatedFiles.length/12)" @click="relatedPage++">下一页</button></div><p v-if="!relatedFiles.length" class="empty">未找到本步骤登记的文件，可在全部文件中查找。</p></template>
      <ResultReport v-else :result="current.record" :files="files" :section="detailTab" />
     </div>
    </main><div v-else class="empty"><h2>选择一个步骤</h2><p>按问题查看结论、图表、核验依据和文件。</p></div>
   </div>
   <template v-else-if="page==='materials'"><h2>题面与方案</h2><nav class="detail-nav" aria-label="资料导航"><button v-for="tab in [{id:'problem',label:'赛题原文'},{id:'model',label:'模型方案'},{id:'data',label:'数据概况'}]" :key="tab.id" :aria-current="materialTab===tab.id ? 'page' : undefined" @click="materialTab=tab.id">{{tab.label}}</button></nav><div class="material-reader" :key="materialTab"><ArtifactContent v-if="materialTab==='problem'" :value="artifacts.problem?.ques_all || '尚未保存题面'"/><template v-else-if="materialTab==='model'"><OverlayDetails :title="artifactLabel(key) + ' · 方案'" v-for="[key,value] in plans" :key="key"><template #trigger>{{artifactLabel(key)}} · 方案</template><ArtifactContent :value="value" /></OverlayDetails><ArtifactContent v-if="!plans.length" :value="artifacts.model || '尚未保存方案'" /></template><ArtifactContent v-else :value="artifacts.data || '尚未保存数据概况'" /></div></template>
   <template v-else><div class="file-heading"><h2>全部文件 <small>{{ files.length }}</small></h2><label><Search :size="15" /><input v-model="filter" aria-label="搜索项目文件" placeholder="搜索文件名" /></label></div><nav class="detail-nav" aria-label="文件分类"><button v-for="kind in [{id:'all',label:'全部'},{id:'figures',label:'图表'},{id:'data',label:'数据与报告'},{id:'code',label:'代码'},{id:'documents',label:'文档与其他'}]" :key="kind.id" :aria-current="fileKind===kind.id ? 'page' : undefined" @click="fileKind=kind.id">{{kind.label}}</button></nav><a v-for="file in fileSlice" :key="file.filename" :href="file.url" target="_blank" rel="noopener" class="file"><FileText :size="16" /><span>{{ file.filename }}</span><small>查看 / 下载 ↗</small></a><p v-if="!visible.length" class="empty">{{ filter ? '没有匹配的文件' : '这个分类还没有文件。' }}</p><div v-if="visible.length" class="pagination"><span>共 {{visible.length}} 项</span><button :disabled="filePage===1" @click="filePage--">上一页</button><span>{{filePage}} / {{filePages}}</span><button :disabled="filePage===filePages" @click="filePage++">下一页</button></div></template>
  </div>
 </section>
</template>
<style scoped>
.project-files{--ink:#242824;--muted:#747b74;--line:#e6e9e4;--surface:#f7f8f5;display:flex;flex-direction:column;flex:1;min-width:0;min-height:0;overflow:hidden;color:var(--ink);padding:24px 32px 0;font-size:13px}.shelf-header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px}h1{font-size:22px;font-weight:600}h2{font-size:18px;font-weight:550}h3{font-size:14px;font-weight:600}.shelf-caption,.muted{font-size:12px;color:var(--muted)}.shelf-caption{margin-top:4px}.refresh-button{display:flex;align-items:center;gap:7px;border:1px solid var(--line);padding:8px 12px;border-radius:8px;white-space:nowrap}.shelf-nav,.detail-nav{display:flex;gap:22px;border-bottom:1px solid var(--line);flex-shrink:0;overflow:auto}.shelf-nav button,.detail-nav button{padding:10px 0;white-space:nowrap;color:var(--muted);border-bottom:2px solid transparent}.shelf-nav [aria-current],.detail-nav [aria-current]{color:var(--ink);border-color:var(--ink);font-weight:550}.shelf-nav time{margin-left:auto;align-self:center;white-space:nowrap;font-size:11px;color:var(--muted)}.sync-status:empty{display:none}.sync-status,.sync-error{font-size:12px;padding:8px 0}.sync-error{color:#955f20}.shelf-body{flex:1;min-height:0;overflow:auto;padding:16px 4px 20px 0;scrollbar-gutter:stable}.overview-heading,.section-heading,.card-heading,.detail-title,.file-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.eyebrow{font-size:11px;color:var(--muted)}.overview-heading h2{margin-top:5px}.status-strip{display:grid;grid-template-columns:repeat(4,1fr);margin:12px 0;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.status-strip>div,.status-strip>button{padding:10px 16px;text-align:left}.status-strip> :not(:last-child){border-right:1px solid var(--line)}.status-strip strong{display:block;font-size:22px;font-weight:550;font-variant-numeric:tabular-nums}.status-strip span{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px;margin-top:3px}.attention-note{display:flex;align-items:flex-start;gap:10px;background:#fcf8ef;color:#875b22;border:1px solid #eee3cc;border-radius:9px;padding:9px 12px;margin:12px 0;font-size:12px;line-height:1.65}.attention-note svg{flex-shrink:0;margin-top:2px}.attention-note button{margin-left:auto;white-space:nowrap}.attention-note p{margin:0}.warning{color:#875b22}.section-heading{margin:16px 0 10px}.section-heading button{font-size:12px;color:var(--muted)}.result-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.result-card{border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;min-width:0}.badge{font-size:11px;border-radius:5px;background:var(--surface);color:var(--muted);padding:3px 7px;white-space:nowrap}.badge.attention{background:#fcf3e4;color:#875b22}.badge.reviewed{background:#eff5eb;color:#4b6840}.result-excerpt{font-size:13px;line-height:1.75;margin:10px 0 12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:46px}.metrics{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px}.metrics>div{min-width:90px;flex:1}.metrics dt{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.metrics dd{font-size:19px;font-weight:550;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;margin:4px 0}.metrics small{font-size:11px;color:var(--muted)}.card-link{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);padding-top:12px;margin-top:auto;font-size:12px}.supporting{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:20px}.supporting button{display:flex;align-items:center;gap:8px;font-size:12px;padding:7px 10px;background:var(--surface);border-radius:6px}.status-dot{width:6px;height:6px;background:#9a9d98;border-radius:50%}.status-dot.attention{background:#ab7839}.status-dot.reviewed{background:#71905b}.detail-layout{display:grid;grid-template-columns:170px minmax(0,1fr);gap:28px;min-height:100%}.step-list{display:flex;flex-direction:column;gap:6px;align-self:start;position:sticky;top:0;max-height:75vh;overflow:auto}.step-list button{text-align:left;padding:12px;border-radius:8px}.step-list [aria-current]{background:var(--surface);box-shadow:inset 3px 0 #b4cd2b}.step-list small{display:block;font-size:10px;margin-top:4px;color:var(--muted)}.detail-content{min-width:0}.back{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);margin-bottom:16px}.detail-title{justify-content:flex-start;margin-bottom:12px}.detail-reader{padding-top:18px;max-width:1050px}.detail-reader section{margin:20px 0}.detail-reader section>p{line-height:1.8;color:#596159}.detail-reader h3{margin-bottom:8px}.detail-metrics{background:var(--surface);border-radius:9px;padding:16px}.material-reader{max-width:1080px;padding:20px 0}.material-reader details{border-bottom:1px solid var(--line);padding:14px 0}.material-reader summary{cursor:pointer;margin-bottom:12px}.file-heading{margin-bottom:14px}.file-heading small{font-size:12px;color:var(--muted)}.file-heading label{display:flex;align-items:center;gap:6px;border:1px solid var(--line);padding:7px 10px;border-radius:7px}.file-heading input{background:transparent;min-width:0;max-width:170px}.file{display:flex;align-items:center;gap:10px;padding:12px 4px;border-bottom:1px solid var(--line);font-size:12px}.file span{flex:1;overflow-wrap:anywhere;min-width:0}.file small{color:var(--muted);white-space:nowrap}.file svg{flex-shrink:0}.pagination{display:flex;align-items:center;justify-content:flex-end;gap:15px;padding:16px 0;font-size:12px}.pagination button{border:1px solid var(--line);padding:5px 10px;border-radius:6px}.empty{padding:36px 12px;color:var(--muted);line-height:2}.empty button{margin-top:14px;color:var(--ink)}button:hover:not(:disabled),a.file:hover{background:#f4f6ef}button:disabled{opacity:.45;cursor:default}button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid #74813e;outline-offset:3px}.spinning{animation:refresh-spin 1s linear infinite}@keyframes refresh-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}@media(max-width:1000px){.project-files{padding:20px 20px 0}.overview-heading{align-items:flex-start}.overview-heading>.muted{max-width:140px}.detail-layout{grid-template-columns:130px minmax(0,1fr);gap:16px}}@media(max-width:640px){.project-files{padding:16px 14px 0}.shelf-nav{gap:20px}.shelf-nav time{display:none}.result-grid{grid-template-columns:1fr}.status-strip>div,.status-strip>button{padding:12px 8px}.status-strip strong{font-size:21px}.status-strip span{font-size:10px}.attention-note{flex-wrap:wrap}.attention-note button{margin-left:28px}.detail-layout{display:block}.step-list{position:static;flex-direction:row;margin-bottom:20px;max-width:100%;overflow:auto}.step-list button{min-width:120px}.detail-nav{gap:18px}.file-heading{align-items:flex-start}.file-heading input{max-width:115px}.overview-heading>.muted{display:none}}
</style>
