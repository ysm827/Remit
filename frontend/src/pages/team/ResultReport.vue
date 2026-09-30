<script setup lang="ts">
import { computed, ref, watch } from "vue";
import ArtifactContent from "./ArtifactContent.vue";
import { artifactLabel, asRecord } from "./artifactLabels";
const props = defineProps<{
	result: unknown;
	section?: "checks" | "figures" | "process";
	files: { filename: string; url: string }[];
}>();
const record = computed(() => asRecord(props.result));
const report = computed(() => asRecord(record.value.quality_report));
const summary = computed(() => asRecord(record.value.execution_summary));
const checks = computed(() =>
	Object.entries(asRecord(report.value.checks)).map(([key, value]) => {
		const check = asRecord(value);
		return {
			name: artifactLabel(key),
			status:
				check.passed === true
					? "通过"
					: check.passed === false
						? "未通过"
						: "未判定",
			value: check.value,
			note: check.note,
		};
	}),
);
const sections = computed(() =>
	Object.entries(report.value).filter(
		([key]) => !["checks", "artifacts", "paper_ready_images"].includes(key),
	),
);
const images = computed(() => {
	const names =
		record.value.paper_ready_images ??
		report.value.paper_ready_images ??
		summary.value.paper_ready_images;
	return Array.isArray(names)
		? props.files.filter(
				(file) =>
					names.includes(file.filename) &&
					/\.(png|jpe?g|webp|gif)$/i.test(file.filename),
			)
		: [];
});
const figurePage = ref(1);
const figurePages = computed(() => Math.max(1, Math.ceil(images.value.length / 4)));
const visibleImages = computed(() => images.value.slice((figurePage.value - 1) * 4, figurePage.value * 4));
watch(() => props.result, () => { figurePage.value = 1; });
const hasReport = computed(() => Object.keys(report.value).length > 0);
</script>
<template>
 <div class="result-report">
  <ArtifactContent v-if="!section && (summary.run_summary || summary.content)" :value="summary.run_summary || summary.content" />
  <p v-if="(!section || section === 'checks') && hasReport" class="report-note">以下为本次计算保存的校验记录；当前审批进度以对话中的状态为准。</p>
  <section v-if="(!section || section === 'checks') && checks.length" class="check-section"><h3>逐项检查</h3><div class="checks-scroll" tabindex="0" aria-label="检查结果，可横向滚动"><table><thead><tr><th scope="col">检查项</th><th scope="col">结果</th><th scope="col">数值</th><th scope="col">说明</th></tr></thead><tbody><tr v-for="check in checks" :key="check.name"><th scope="row">{{ check.name }}</th><td><span :class="{ issue: check.status === '未通过' }">{{ check.status }}</span></td><td>{{ check.value ?? '—' }}</td><td>{{ check.note || '未提供说明' }}</td></tr></tbody></table></div></section>
  <section v-for="[key, value] in (!section || section === 'checks' ? sections : [])" :key="key" class="report-section"><h3>{{ artifactLabel(key) }}</h3><ArtifactContent :value="value" :field="key" /></section>
  <section v-if="(!section || section === 'figures') && images.length" class="report-section"><h3>结果图表</h3><div class="figures"><figure v-for="file in visibleImages" :key="file.filename"><a :href="file.url" target="_blank" rel="noopener"><img :src="file.url" :alt="file.filename" loading="lazy" /></a><figcaption>{{ file.filename }}</figcaption></figure></div><nav v-if="figurePages > 1" class="figure-pages" aria-label="图表分页"><button :disabled="figurePage===1" @click="figurePage--">上一页</button><span>{{figurePage}} / {{figurePages}} · 共 {{images.length}} 张</span><button :disabled="figurePage===figurePages" @click="figurePage++">下一页</button></nav></section>
  <section v-if="(!section || section === 'checks') && record.modeler_review" class="report-section"><h3>建模复核</h3><ArtifactContent :value="record.modeler_review" /></section>
  <details v-if="!section && hasReport && record.coder_response"><summary>计算过程</summary><ArtifactContent :value="record.coder_response" /></details>
  <ArtifactContent v-if="section === 'process' || (!section && !hasReport)" :value="record.coder_response ?? result" />
  <p v-if="section === 'figures' && !images.length" class="report-note">本步骤尚未登记结果图表。可在相关文件中查看其他产物。</p>
  <p v-if="section === 'checks' && !hasReport && !record.modeler_review" class="report-note">尚未保存核验报告，不能据此判断结果通过。</p>
 </div>
</template>
<style scoped>
.result-report{min-width:0}.figure-pages{display:flex;justify-content:center;gap:18px;font-size:12px;padding:16px}.figure-pages button:disabled{opacity:.4}.figure-pages button:focus-visible{outline:2px solid #74813e;outline-offset:3px}.report-note{color:#777;font-size:12px;line-height:1.7;margin:12px 0 22px}.report-section,.check-section{margin:24px 0}.result-report h3{font-size:13px;font-weight:600;margin-bottom:10px}.checks-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;line-height:1.75;text-align:left}th,td{border-bottom:1px solid #e8e8e8;padding:10px 14px;vertical-align:top}thead{background:#f7f7f7;color:#666}th{font-weight:500}th:first-child{min-width:145px}td:nth-child(2){white-space:nowrap}td:last-child{min-width:230px}.issue{color:#9a4e12}.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px}.figures img{width:100%;height:auto;border:1px solid #eee;border-radius:6px}.figures figcaption{color:#777;font-size:12px;margin-top:8px;overflow-wrap:anywhere}summary{cursor:pointer;font-size:13px;color:#666;padding:12px 0}details{border-top:1px solid #eee;margin-top:24px}.checks-scroll:focus-visible,summary:focus-visible{outline:2px solid #666;outline-offset:3px}
</style>
