<script setup lang="ts">
import { explainModelingSubmissionFailure } from "@/apis/submitModelingApi";
import type { CompetitionProfile } from "@/apis/teamApi";
import request from "@/utils/request";
import { X } from "lucide-vue-next";
import { ref } from "vue";
const props = defineProps<{ task_id: string }>();
const open = ref(false);
const report = ref<{
	competition: CompetitionProfile;
	checks: { label: string; status: string }[];
} | null>(null);
const error = ref("");
async function inspect() {
	open.value = true;
	try {
		report.value = (
			await request.get(
				`/api/competitions/project/${encodeURIComponent(props.task_id)}/review`,
			)
		).data;
		error.value = "";
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
	}
}
</script>
<template><button @click="inspect">交付检查</button><Teleport to="body"><div v-if="open" class="contest-overlay" @click.self="open = false"><section class="contest-review" role="dialog" aria-modal="true" aria-label="赛事交付检查"><header><h2>{{ report?.competition.name || '赛事交付检查' }} {{ report?.competition.year }}</h2><button aria-label="关闭交付检查" @click="open = false"><X :size="18" /></button></header><p v-if="error" role="alert">{{ error }}</p><p>自动检查覆盖以下条目，其余内容请结合本届通知核对。</p><ul><li v-for="check in report?.checks" :key="check.label"><span :class="check.status">{{ {passed:'通过',failed:'需修复',pending:'待完成',manual:'人工核对'}[check.status] }}</span>{{ check.label }}</li></ul><footer><a v-for="source in report?.competition.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener">赛事资料 ↗</a><small>下载项目时同时导出此清单和真实 AI 交互记录。</small></footer></section></div></Teleport></template>
<style scoped>.contest-overlay{position:fixed;inset:0;z-index:110;background:#0004;display:grid;place-items:center;padding:20px;font:13px/1.7 Inter,"Microsoft YaHei",sans-serif;color:#333}.contest-review{width:620px;max-width:100%;max-height:85vh;overflow:auto;background:#fff;border-radius:10px;padding:24px}.contest-review header{display:flex;justify-content:space-between;gap:15px;align-items:center}.contest-review h2{font-weight:600;font-size:17px}.contest-review p{color:#777;margin:15px 0}.contest-review li{display:flex;gap:14px;padding:12px 0;border-bottom:1px solid #eee}.contest-review li span{flex-shrink:0;color:#666;font-size:11px;min-width:50px}.contest-review .passed{color:#458343}.contest-review .failed{color:#b74637}.contest-review footer{margin-top:20px;display:flex;flex-direction:column;gap:9px}.contest-review a{text-decoration:underline}.contest-review small{color:#888}</style>
