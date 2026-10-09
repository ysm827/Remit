<script setup lang="ts">
import FloatingPanel from "./FloatingPanel.vue";
import { type MarkdownContext, renderMarkdown } from "@/utils/markdown";
import { computed, inject, ref, useId } from "vue";
import { artifactLabel, asRecord, readableValue } from "./artifactLabels";

const props = defineProps<{ value: unknown; field?: string }>();
const markdownContext = inject<() => MarkdownContext>(
	"artifactMarkdownContext",
	() => ({}),
);
const expanded = ref(false);
const id = useId();
// Some historical records contain a JSON string inside the structured response.
const value = computed(() => {
	if (typeof props.value !== "string") return props.value;
	const raw = props.value
		.trim()
		.replace(/^```json\s*/i, "")
		.replace(/\s*```$/, "");
	if (!/^[{[]/.test(raw)) return props.value;
	try {
		return JSON.parse(raw);
	} catch {
		return props.value;
	}
});
const entries = computed(() => Object.entries(asRecord(value.value)));
const rows = computed(() => (Array.isArray(value.value) ? value.value : []));
const columns = computed(() => {
	if (
		!rows.value.length ||
		!rows.value.every((row) => Object.keys(asRecord(row)).length > 0)
	)
		return [];
	const keys = [...new Set(rows.value.flatMap((row) => Object.keys(row)))];
	return keys.length <= 7 &&
		rows.value.every((row) =>
			Object.values(row).every(
				(cell) => cell == null || typeof cell !== "object",
			),
		)
		? keys
		: [];
});
const text = computed(() => readableValue(value.value, props.field));
// Preview and reader share one sanitized rendering, including expensive formulas.
const html = computed(() => renderMarkdown(text.value, {}, markdownContext()));
const long = computed(
	() => text.value.length > 650 || text.value.split("\n").length > 10,
);
</script>

<template>
 <div class="artifact-content">
  <div v-if="columns.length" class="table-scroll" tabindex="0" aria-label="数据表格，可横向滚动"><table><thead><tr><th v-for="key in columns" :key="key" scope="col">{{ artifactLabel(key) }}</th></tr></thead><tbody><tr v-for="(row, i) in rows" :key="i"><td v-for="key in columns" :key="key">{{ readableValue(row[key], key) }}</td></tr></tbody></table></div>
  <ul v-else-if="Array.isArray(value) && rows.length" class="content-list"><li v-for="(row, i) in rows" :key="i"><ArtifactContent :value="row" :field="field" /></li></ul>
  <dl v-else-if="entries.length" class="content-fields"><div v-for="[key, item] in entries" :key="key"><dt>{{ artifactLabel(key) }}</dt><dd><ArtifactContent :value="item" :field="key" /></dd></div></dl>
  <p v-else-if="value !== null && typeof value === 'object'" class="muted">暂无记录</p>
  <template v-else>
   <div :id="id" class="reader" :class="{ clipped: long }" v-html="html" />
   <button v-if="long" class="expand" :aria-expanded="expanded" :aria-controls="`${id}-reader`" aria-haspopup="dialog" @click="expanded = true">查看全文</button><FloatingPanel :id="`${id}-reader`" v-model:open="expanded" title="完整正文" :width="680"><div class="reader" v-html="html" /></FloatingPanel>
  </template>
 </div>
</template>

<style scoped>
.artifact-content{min-width:0;font-size:14px;line-height:1.85;overflow-wrap:anywhere}.content-fields{margin:0}.content-fields>div{margin:0 0 20px}.content-fields dt{font-size:13px;font-weight:600;margin-bottom:5px}.content-fields dd{margin:0}.content-fields .content-fields{border-left:2px solid #eee;padding-left:18px}.content-list{padding-left:20px;list-style:disc}.content-list>li{margin:8px 0}.muted{color:#777}.clipped{max-height:260px;overflow:hidden;mask-image:linear-gradient(#000 75%,transparent)}.expand{font-size:12px;color:#626262;margin-top:10px;padding:4px 0}.expand:hover{color:#111}.expand:focus-visible,.table-scroll:focus-visible{outline:2px solid #666;outline-offset:4px}.table-scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:10px 14px;border-bottom:1px solid #e8e8e8;vertical-align:top;min-width:85px}th{font-weight:500;background:#f7f7f7;color:#666}.reader :deep(p){margin:0 0 12px}.reader :deep(h1),.reader :deep(h2),.reader :deep(h3){font-size:15px;font-weight:600;margin:18px 0 8px}.reader :deep(ul){list-style:disc;padding-left:22px}.reader :deep(ol){list-style:decimal;padding-left:22px}.reader :deep(table){display:block;overflow:auto;border-collapse:collapse}.reader :deep(th),.reader :deep(td){border:1px solid #e8e8e8;padding:8px 12px}.reader :deep(pre){overflow:auto;max-width:100%;padding:14px;background:#f7f7f7;font-size:12px}.reader :deep(img){max-width:100%;height:auto}.reader :deep(a){text-decoration:underline}.reader :deep(.katex-display){overflow:auto}
</style>
