<script setup lang="ts">
import request from "@/utils/request";
import { computed, onMounted, ref, watch } from "vue";

interface Profile {
	error?: { message?: string };
	[key: string]: unknown;
	requirements?: {
		label: string;
		needs_tools: boolean;
		needs_vision: boolean;
		max_calls: number;
		max_output_tokens: number;
		structured_mode: string;
	};
	errors?: Record<string, { status: string; message: string }>;
	checked_at?: string;
}
const roles = {
	coordinator: "协调手",
	modeler: "建模手",
	coder: "代码手",
	writer: "论文手",
	vision: "赛题识图",
	model_scout: "模型探索者",
	model_critic: "模型盲审者",
};
const role = ref<keyof typeof roles>("coder");
const connection = ref("primary");
const profileKey = computed(() => connection.value === "fallback" ? `fallback:${role.value}` : role.value);
const profiles = ref<Record<string, Profile>>({});
const consent = ref(false);
const busy = ref(false);
const error = ref("");
let revision = 0;
watch([role, connection], () => {
	consent.value = false;
	error.value = "";
});
const profile = computed(() => profiles.value[profileKey.value]);
const requirements = computed(() => profile.value?.requirements);
const labels: Record<string, string> = {
	connection: "连接",
	text: "非空文本",
	structured_output: "结构化输出",
	tools: "工具调用",
	tool_result: "工具结果回传",
	vision: "图片识别",
};
const checks = computed(() => [
	"connection",
	"text",
	"structured_output",
	...(requirements.value?.needs_tools ? ["tools", "tool_result"] : []),
	...(requirements.value?.needs_vision ? ["vision"] : []),
]);
function verdict(key: string) {
	if (profile.value?.errors?.[key]?.status === "verification_failed")
		return "本次请求失败，能力仍未知";
	return (
		(
			{
				supported: "已验证",
				unsupported: "本次能力测试未通过",
				unknown: "尚未验证",
			} as Record<string, string>
		)[String(profile.value?.[key] || "unknown")] || "尚未验证"
	);
}
onMounted(async () => {
	const current = revision;
	try {
		const response = await request.get("/api/model-capabilities");
		if (current === revision) profiles.value = response.data;
	} catch {
		error.value = "无法读取检查范围，请重新打开设置。";
	}
});
async function verify() {
	if (!consent.value || busy.value || !requirements.value) return;
	const selected = role.value;
	const selectedKey = profileKey.value;
	const fallback = connection.value === "fallback";
	revision += 1;
	busy.value = true;
	error.value = "";
	try {
		const response = await request.post(
			"/api/model-capabilities",
			{ role: selected, authorized: true, ...(fallback ? { fallback: true } : {}) },
			{ timeout: 300000 },
		);
		profiles.value[selectedKey] = response.data;
	} catch {
		error.value =
			"验证未完成，请确认已保存完整配置。已有记录保留；本次失败不代表模型不支持。";
	} finally {
		busy.value = false;
	}
}
</script>

<template>
	<section class="rounded-md border p-3 space-y-2" aria-label="模型能力验证">
		<h3 class="text-sm font-medium">验证已保存模型的实际能力</h3>
		<select v-model="role" :disabled="busy" aria-label="验证角色" class="text-sm border rounded p-1"><option v-for="(name, key) in roles" :key="key" :value="key">{{ name }}</option></select>
		<select v-model="connection" :disabled="busy" aria-label="验证连接" class="text-sm border rounded p-1"><option value="primary">当前角色连接</option><option value="fallback">备用模型连接</option></select>
        <p v-if="connection === 'fallback'" class="text-xs text-muted-foreground">按所选角色验证备用模型。含图片的请求还需通过“赛题识图”的备用验证；只有选择该角色时才发送测试图片。切换前会核对本次请求的能力与容量。</p>
        <p v-if="requirements" class="text-xs text-muted-foreground">本角色检查{{ requirements.structured_mode === 'json_text_and_tool_arguments' ? 'JSON 文本、工具参数与结果回传' : requirements.structured_mode === 'tool_arguments' ? '工具参数 JSON 与结果回传' : '提示词 JSON 文本' }}{{ requirements.needs_vision ? '及图片识别；仅发送本地生成的随机数字和彩色方块图片' : '' }}。最多 {{ requirements.max_calls }} 次请求，每次最多 {{ requirements.max_output_tokens }} 输出 token，按供应商计费。通过仅表示这组小样本可用。</p>
		<p v-if="role === 'vision'" class="text-xs text-muted-foreground">采用实际识图配置；未单独配置的连接字段沿用协调手。其他角色不要求支持图片。</p>
		<label class="flex gap-2 text-xs"><input v-model="consent" type="checkbox" :disabled="busy" />我授权上述调用次数与输出上限，费用按供应商价格计算</label>
		<button class="rounded border px-3 py-1 text-sm disabled:opacity-50" :disabled="!consent || busy || !requirements" @click="verify">{{ busy ? '正在验证…' : '验证模型能力' }}</button>
		<p v-if="error" role="alert" class="text-xs">{{ error }}</p>
		<div v-if="profile" class="text-xs space-y-1" role="status">
			<p v-for="key in checks" :key="key">{{ labels[key] }}：{{ verdict(key) }}</p>
			<p v-if="profile.checked_at">验证时间：{{ new Date(profile.checked_at).toLocaleString() }}</p>
			<p v-if="profile.error">{{ profile.error.message || "部分检查未完成；未测能力保持未知，可稍后重新验证。" }}</p>
		</div>
	</section>
</template>
