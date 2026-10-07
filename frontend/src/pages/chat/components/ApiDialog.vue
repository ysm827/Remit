<script setup lang="ts">
import ComposerSelect from "@/pages/team/ComposerSelect.vue";
import {
	type AgentApiConfigStatus,
	getApiConfigStatus,
	saveApiConfig,
	validateApiKey,
	validateOpenalexEmail,
} from "@/apis/apiKeyApi";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useApiKeyStore } from "@/stores/apiKeys";
import { explainValidationFailure } from "@/utils/apiValidation";
import type { ModelConfig } from "@/utils/interface";
import {
	CheckCircle,
	Cable,
	ShieldCheck,
	Users,
	BookOpen,
	Waypoints,
	CircleAlert,
	LoaderCircle,
	XCircle,
} from "lucide-vue-next";
import { computed, reactive, ref, watch } from "vue";
import CapabilityPanel from "./CapabilityPanel.vue";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<(e: "update:open", value: boolean) => void>();

const apiKeyStore = useApiKeyStore();

/** API 类型选项（取值即后端 ApiType 线协议） */
const API_TYPE_OPTIONS = [
	{ value: "openai-chat", label: "OpenAI Chat" },
	{ value: "openai-responses", label: "OpenAI Responses" },
	{ value: "anthropic", label: "Anthropic" },
	{ value: "gemini", label: "Gemini 原生" },
];

type AgentKey =
	| "coordinator"
	| "modeler"
	| "coder"
	| "writer"
	| "model_scout"
	| "model_critic"
	| "fallback";

interface AgentFormConfig {
	apiKey: string;
	baseUrl: string;
	modelId: string;
	apiType: string;
	contextWindow: number;
    maxTokens?: number;
}

interface AgentFieldMeta {
	key: AgentKey;
	label: string;
	defaultContextWindow: number;
	councilOnly: boolean;
}

/** 角色连接与可选备用连接共用表单。 */
const AGENT_FIELDS: AgentFieldMeta[] = [
	{ key: "fallback", label: "备用模型连接", defaultContextWindow: 128000, councilOnly: false },
	{
		key: "coordinator",
		label: "协调者模型配置",
		defaultContextWindow: 128000,
		councilOnly: false,
	},
	{
		key: "modeler",
		label: "主建模手模型配置",
		defaultContextWindow: 128000,
		councilOnly: false,
	},
	{
		key: "coder",
		label: "代码手模型配置",
		defaultContextWindow: 128000,
		councilOnly: false,
	},
	{
		key: "writer",
		label: "论文手模型配置",
		defaultContextWindow: 128000,
		councilOnly: false,
	},
	{
		key: "model_scout",
		label: "候选模型探索（独立）",
		defaultContextWindow: 262144,
		councilOnly: true,
	},
	{
		key: "model_critic",
		label: "方案盲审与质疑（独立）",
		defaultContextWindow: 262144,
		councilOnly: true,
	},
];

function blankAgentForm(contextWindow: number): AgentFormConfig {
	return { apiKey: "", baseUrl: "", modelId: "", apiType: "", contextWindow };
}

function buildEmptyAgentForms(): Record<AgentKey, AgentFormConfig> {
	return Object.fromEntries(
		AGENT_FIELDS.map((field) => [
			field.key,
			blankAgentForm(field.defaultContextWindow),
		]),
	) as Record<AgentKey, AgentFormConfig>;
}

/** 本地表单数据 */
const agentForms = reactive(buildEmptyAgentForms());
const modelCouncilEnabled = ref(false);
const sharedCore = ref(true);
const fallbackEnabled = ref(false);
const capabilityRevision = ref(0);
const openalexEmail = ref("");

/** 验证加载状态 */
const validating = ref(false);
const saving = ref(false);
const statusLoading = ref(false);
const statusError = ref("");
const saveError = ref("");
const saveSuccess = ref("");
const effectiveAgents = ref<Partial<Record<AgentKey, AgentApiConfigStatus>>>(
	{},
);

type Verdict = { valid: boolean; message: string };

function blankVerdicts(): Record<AgentKey | "openalex_email", Verdict> {
	const verdicts = {} as Record<AgentKey | "openalex_email", Verdict>;
	for (const field of AGENT_FIELDS) {
		verdicts[field.key] = { valid: false, message: "" };
	}
	verdicts.openalex_email = { valid: false, message: "" };
	return verdicts;
}

/** 各配置项的验证结果 */
const validationResults = ref(blankVerdicts());

const SETTINGS_PAGES = [
	{ key: "connections", label: "模型连接", description: "配置小队使用的模型与服务商。", icon: Cable },
	{ key: "fallback", label: "备用模型", description: "主连接失败时使用的备用连接。", icon: Waypoints },
	{ key: "council", label: "模型评审组", description: "独立探索候选方案，再进行匿名盲审。", icon: Users },
	{ key: "capabilities", label: "能力验证", description: "先保存连接，再验证模型的实际能力。", icon: ShieldCheck },
	{ key: "literature", label: "文献服务", description: "管理文献检索使用的联系信息。", icon: BookOpen },
] as const;
type SettingsPage = typeof SETTINGS_PAGES[number]["key"];
const activePage = ref<SettingsPage>("connections");
const contentPane = ref<HTMLElement | null>(null);
watch(activePage, () => { if (contentPane.value) contentPane.value.scrollTop = 0; });
const selectedCore = ref<AgentKey>("coordinator");
const selectedCouncil = ref<AgentKey>("model_scout");
const currentPage = computed(() => SETTINGS_PAGES.find((page) => page.key === activePage.value) ?? SETTINGS_PAGES[0]);
const coreFields = AGENT_FIELDS.filter((field) => field.key !== "fallback" && !field.councilOnly);
const councilFields = AGENT_FIELDS.filter((field) => field.councilOnly);
const activeFields = computed(() => {
	const key = activePage.value === "connections"
		? sharedCore.value ? "coordinator" : selectedCore.value
		: activePage.value === "fallback" && fallbackEnabled.value ? "fallback"
		: activePage.value === "council" && modelCouncilEnabled.value ? selectedCouncil.value : null;
	return AGENT_FIELDS.filter((field) => field.key === key);
});

/** 从 store 加载数据到表单 */
function loadFromStore(): void {
	const storeConfigs: Record<AgentKey, ModelConfig> = {
		fallback: { ...blankAgentForm(128000), maxTokens: 8192 },
		coordinator: apiKeyStore.coordinatorConfig,
		modeler: apiKeyStore.modelerConfig,
		coder: apiKeyStore.coderConfig,
		writer: apiKeyStore.writerConfig,
		model_scout: apiKeyStore.modelScoutConfig,
		model_critic: apiKeyStore.modelCriticConfig,
	};
	for (const field of AGENT_FIELDS) {
		agentForms[field.key] = {
			...storeConfigs[field.key],
			contextWindow:
				storeConfigs[field.key].contextWindow ?? field.defaultContextWindow,
		};
	}
	modelCouncilEnabled.value = apiKeyStore.modelCouncilEnabled;
	openalexEmail.value = apiKeyStore.openalexEmail;
}

function sourceLabel(source?: AgentApiConfigStatus["source"]): string {
	switch (source) {
		case "runtime":
			return "界面设置";
		case "environment":
			return "后端环境";
		default:
			return "未配置";
	}
}

/** 读取后端当前真正用于创建 Agent 的有效配置，密钥只返回是否存在。 */
async function loadEffectiveConfig(): Promise<boolean> {
	statusLoading.value = true;
	statusError.value = "";
	try {
		const response = await getApiConfigStatus();
		const agents = response.data.agents as Record<
			AgentKey,
			AgentApiConfigStatus
		>;
		effectiveAgents.value = agents;
		fallbackEnabled.value = response.data.fallback_enabled === true;
		sharedCore.value =
			response.data.shared_core === true ||
			Object.values(agents).every((agent) => !agent.configured);
		modelCouncilEnabled.value = response.data.model_council_enabled;
		apiKeyStore.setModelCouncilEnabled(response.data.model_council_enabled);

		for (const field of AGENT_FIELDS) {
			const current = agents[field.key];
			if (!current) {
				continue;
			}
			agentForms[field.key] = {
				...agentForms[field.key],
				apiType: current.api_type || "",
				baseUrl: current.base_url || "",
				modelId: current.model_id || "",
				contextWindow: current.context_window || field.defaultContextWindow,
                ...(field.key === "fallback" ? { maxTokens: current.max_tokens ?? 8192 } : {}),
			};
		}
		return true;
	} catch (error) {
		console.error("读取当前有效 API 配置失败:", error);
		statusError.value = "无法读取后端当前配置，请确认后端服务已启动";
		return false;
	} finally {
		statusLoading.value = false;
	}
}

/** 保存表单数据到 store 和后端 */
async function saveToStore(): Promise<boolean> {
	apiKeyStore.setCoordinatorConfig(agentForms.coordinator);
	apiKeyStore.setModelerConfig(agentForms.modeler);
	apiKeyStore.setCoderConfig(agentForms.coder);
	apiKeyStore.setWriterConfig(agentForms.writer);
	apiKeyStore.setModelScoutConfig(agentForms.model_scout);
	apiKeyStore.setModelCriticConfig(agentForms.model_critic);
	apiKeyStore.setModelCouncilEnabled(modelCouncilEnabled.value);
	apiKeyStore.setOpenalexEmail(openalexEmail.value);

	saving.value = true;
	saveError.value = "";
	saveSuccess.value = "";
	try {
		const response = await saveApiConfig({
			...agentForms,
			shared_core: sharedCore.value,
			fallback_enabled: fallbackEnabled.value,
			model_council_enabled: modelCouncilEnabled.value,
			openalex_email: openalexEmail.value,
		});
		capabilityRevision.value += 1;
		if (!(await loadEffectiveConfig())) {
			throw new Error("保存后无法读取后端有效配置");
		}
		const missingAgents = AGENT_FIELDS.filter(
			(field) =>
				(field.key === "fallback" ? fallbackEnabled.value : !field.councilOnly || modelCouncilEnabled.value) &&
				!effectiveAgents.value[field.key]?.configured,
		).map((field) => field.label);
		if (missingAgents.length) {
			throw new Error(`保存后配置仍不完整: ${missingAgents.join("、")}`);
		}
		saveSuccess.value = response.data.message;
		return true;
	} catch (error) {
		console.error("保存配置到后端失败:", error);
		saveError.value =
			error instanceof Error && error.message.startsWith("保存后配置仍不完整")
				? error.message
				: "配置未保存，请确认 Remit 后端仍在运行后重试";
		return false;
	} finally {
		saving.value = false;
	}
}

watch(
	() => props.open,
	(open) => {
		if (!open) {
			return;
		}
		loadFromStore();
		saveError.value = "";
		saveSuccess.value = "";
		void loadEffectiveConfig();
	},
	{ immediate: true },
);

function updateOpen(value: boolean): void {
	emit("update:open", value);
}

/** 验证大模型 API Key；留空密钥时尝试沿用后端已生效配置 */
async function validateModelApiKey(
	config: AgentFormConfig,
	key: AgentKey,
): Promise<Verdict> {
	if (!config.apiKey) {
		const effective = effectiveAgents.value[key];
		const identity = [
			effective?.api_type,
			effective?.model_id,
			effective?.base_url,
		];
		const formIdentity = [config.apiType, config.modelId, config.baseUrl];
		const canReuse = Boolean(
			effective?.configured &&
				identity.every((value, index) => (value || "") === formIdentity[index]),
		);
		return canReuse
			? { valid: false, message: "已保存密钥；连接和能力仍需主动验证" }
			: { valid: false, message: "请填写 API Key，或恢复后端当前模型配置" };
	}

	if (!config.modelId) {
		return { valid: false, message: "Model ID 为空" };
	}

	try {
		const { data } = await validateApiKey({
			api_key: config.apiKey,
			base_url: config.baseUrl || "https://api.openai.com/v1",
			model_id: config.modelId,
			api_type: config.apiType || "openai-chat",
		});
		return data;
	} catch (error) {
		return { valid: false, message: explainValidationFailure(error) };
	}
}

async function validateOpenAlexSetting(): Promise<Verdict> {
	const email = openalexEmail.value.trim();
	if (!email) return { valid: true, message: "未填写，可稍后配置" };
	try {
		return (await validateOpenalexEmail({ email })).data;
	} catch (error) {
		return { valid: false, message: explainValidationFailure(error) };
	}
}

/** 只测试当前连接，避免分页后发起看不见的其他角色请求。 */
async function validateCurrentConnection(): Promise<void> {
	if (validating.value) return;
	const field = activeFields.value[0];
	validating.value = true;
	try {
		if (field) {
			validationResults.value[field.key] = { valid: false, message: "正在连接…" };
			validationResults.value[field.key] = await validateModelApiKey(agentForms[field.key], field.key);
		} else if (activePage.value === "literature") {
			validationResults.value.openalex_email = await validateOpenAlexSetting();
		}
	} finally {
		validating.value = false;
	}
}

function resetCurrentConnection(): void {
	for (const field of activeFields.value) {
		agentForms[field.key] = { ...blankAgentForm(field.defaultContextWindow), ...(field.key === "fallback" ? { maxTokens: 8192 } : {}) };
		validationResults.value[field.key] = { valid: false, message: "" };
	}
	if (activePage.value === "literature") {
		openalexEmail.value = "";
		validationResults.value.openalex_email = { valid: false, message: "" };
	}
	saveError.value = "";
	saveSuccess.value = "";
}
</script>

<template>
  <Dialog :open="props.open" @update:open="updateOpen">
    <DialogContent class="settings-dialog max-w-none gap-0 p-0">
      <DialogHeader class="settings-header">
        <DialogTitle class="text-xl">设置</DialogTitle>
        <DialogDescription class="sr-only">按分类管理模型连接、备用模型、评审组、能力验证和文献服务。</DialogDescription>
        <div class="settings-status" role="status">
          <template v-if="statusLoading"><LoaderCircle class="h-3.5 w-3.5 animate-spin" />正在读取后端当前生效配置…</template>
          <template v-else-if="!statusError && Object.keys(effectiveAgents).length"><CheckCircle class="h-3.5 w-3.5" />已读取后端实际配置</template>
        </div>
      </DialogHeader>

      <div class="settings-body">
        <nav class="settings-nav" aria-label="设置分类">
          <button v-for="page in SETTINGS_PAGES" :key="page.key" type="button"
            :aria-current="activePage === page.key ? 'page' : undefined"
            :class="{ selected: activePage === page.key }" @click="activePage = page.key">
            <component :is="page.icon" class="h-4 w-4" aria-hidden="true" />{{ page.label }}
          </button>
        </nav>
        <label class="settings-mobile-nav">设置分类
          <ComposerSelect :model-value="activePage" @update:model-value="activePage = $event as SettingsPage" label="设置分类" title="设置分类" :options="SETTINGS_PAGES.map(page=>({value:page.key,label:page.label}))" />
        </label>

        <main ref="contentPane" class="settings-content" :aria-label="currentPage.label">
          <div class="settings-page-heading">
            <h3>{{ currentPage.label }}</h3>
            <p>{{ currentPage.description }}</p>
          </div>

          <div v-if="activePage === 'connections'" class="settings-section-intro">
            <label class="settings-toggle"><span>四位角色共用协调者的模型连接</span><input v-model="sharedCore" type="checkbox" /></label>
            <div v-if="!sharedCore" class="settings-role-picker" role="group" aria-label="选择小队角色">
              <button v-for="field in coreFields" :key="field.key" type="button" :aria-pressed="selectedCore === field.key"
                @click="selectedCore = field.key">{{ field.label.replace('模型配置', '') }}</button>
            </div>
            <p v-else class="settings-hint">四位角色使用同一连接，只需填写一次。</p>
          </div>

          <div v-else-if="activePage === 'fallback'" class="settings-section-intro">
            <label class="settings-toggle"><span>启用备用模型</span><input v-model="fallbackEnabled" type="checkbox" /></label>
            <p class="settings-hint">主连接持续失败时，在相同服务地址与协议内切换。保存后需在能力验证中检查备用连接。</p>
            <p v-if="!fallbackEnabled" class="settings-empty">启用后可配置备用模型的连接和容量。</p>
          </div>

          <div v-else-if="activePage === 'council'" class="settings-section-intro">
            <label class="settings-toggle"><span>启用多模型建模评审组</span><input v-model="modelCouncilEnabled" type="checkbox" /></label>
            <div v-if="modelCouncilEnabled" class="settings-role-picker" role="group" aria-label="选择评审角色">
              <button v-for="field in councilFields" :key="field.key" type="button" :aria-pressed="selectedCouncil === field.key"
                @click="selectedCouncil = field.key">{{ field.key === 'model_scout' ? '候选探索' : '匿名盲审' }}</button>
            </div>
            <p v-else class="settings-empty">启用后，分别配置候选探索与匿名盲审使用的模型。</p>
          </div>

          <section v-for="field in activeFields" :key="field.key" class="settings-connection" :aria-label="field.label">
            <div class="settings-connection-heading">
              <h4>{{ field.label }}</h4>
              <span v-if="effectiveAgents[field.key]" class="settings-hint">
                {{ effectiveAgents[field.key]?.configured ? '已配置' : '未配置完整' }} · {{ sourceLabel(effectiveAgents[field.key]?.source) }}
              </span>
            </div>
            <div class="settings-form-grid">
              <div class="settings-field">
                <Label :for="`${field.key}-api-type`">API 类型</Label>
                <Select v-model="agentForms[field.key].apiType">
                  <SelectTrigger :id="`${field.key}-api-type`"><SelectValue placeholder="选择 API 类型" /></SelectTrigger>
                  <SelectContent><SelectGroup><SelectLabel>API 类型</SelectLabel>
                    <SelectItem v-for="opt in API_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
                  </SelectGroup></SelectContent>
                </Select>
              </div>
              <div class="settings-field">
                <Label :for="`${field.key}-api-key`">API Key</Label>
                <Input :id="`${field.key}-api-key`" v-model.trim="agentForms[field.key].apiKey" type="password" autocomplete="off"
                  :placeholder="effectiveAgents[field.key]?.api_key_configured ? '已保存，留空继续使用' : '请输入 API Key'" />
              </div>
              <div class="settings-field">
                <Label :for="`${field.key}-base-url`">Base URL</Label>
                <Input :id="`${field.key}-base-url`" v-model.trim="agentForms[field.key].baseUrl" placeholder="https://api.openai.com/v1" />
              </div>
              <div class="settings-field">
                <Label :for="`${field.key}-model-id`">Model ID</Label>
                <Input :id="`${field.key}-model-id`" v-model.trim="agentForms[field.key].modelId" placeholder="服务商提供的模型 ID" />
              </div>
              <div class="settings-field">
                <Label :for="`${field.key}-context-window`">上下文窗口（token）</Label>
                <Input :id="`${field.key}-context-window`" v-model.number="agentForms[field.key].contextWindow" type="number" min="4096" step="1024" />
              </div>
              <div v-if="field.key === 'fallback'" class="settings-field">
                <Label for="fallback-max-tokens">单次输出上限（token）</Label>
                <Input id="fallback-max-tokens" v-model.number="agentForms.fallback.maxTokens" type="number" min="1" step="1024" />
              </div>
            </div>
            <p class="settings-hint">密钥不会回显；留空沿用已保存的密钥。{{ field.key === 'fallback' ? '容量或输出上限修改后需重新验证。' : '已有配置不代表能力验证通过。' }}</p>
            <div class="settings-connection-actions">
              <Button variant="outline" size="sm" :disabled="validating || saving || statusLoading" @click="validateCurrentConnection">
                {{ validating ? '验证中…' : '测试当前文本连接（可能计费）' }}
              </Button>
              <button type="button" class="settings-text-button" @click="activePage = 'capabilities'">前往能力验证 →</button>
            </div>
            <p v-if="validationResults[field.key].message" role="status" class="settings-hint">{{ validationResults[field.key].message }}</p>
          </section>

          <p v-if="activePage === 'council'" class="settings-hint settings-note">AI 提出方案 → 主建模手综合 → 同口径实测。最终方案仍需人工确认。</p>

          <section v-if="activePage === 'literature'" class="settings-literature">
            <div class="settings-field">
              <Label for="openalex-email">OpenAlex Email</Label>
              <Input id="openalex-email" v-model.trim="openalexEmail" placeholder="用于文献检索的联系邮箱" />
            </div>
            <p class="settings-hint">可选。了解 <a href="https://openalex.org/" target="_blank" rel="noopener noreferrer">OpenAlex 文献服务 ↗</a></p>
            <Button variant="outline" size="sm" :disabled="validating || saving" @click="validateCurrentConnection">{{ validating ? '检查中…' : '检查邮箱设置' }}</Button>
            <p v-if="validationResults.openalex_email.message" role="status" class="settings-hint">{{ validationResults.openalex_email.message }}</p>
          </section>
          <!-- 切换分类不丢失正在进行的验证。 -->
          <div v-show="activePage === 'capabilities'" class="settings-capabilities">
            <CapabilityPanel :key="capabilityRevision" />
          </div>
        </main>
      </div>

      <footer class="settings-footer">
        <div class="settings-footer-status">
          <div v-if="statusError" role="alert" class="settings-error"><CircleAlert class="h-4 w-4 shrink-0" /><span>{{ statusError }}</span><button type="button" @click="loadEffectiveConfig">重试读取</button></div>
          <div v-else-if="saveError" role="alert" class="settings-error"><XCircle class="h-4 w-4 shrink-0" /><span>{{ saveError }}</span></div>
          <span v-else-if="saveSuccess" role="status">{{ saveSuccess }}</span>
          <span v-else>切换分类保留编辑，保存后生效</span>
        </div>
        <div class="settings-footer-actions">
          <Button v-if="activeFields.length || activePage === 'literature'" variant="ghost" size="sm" :disabled="validating || saving" @click="resetCurrentConnection">清空当前页</Button>
          <Button variant="outline" size="sm" :disabled="saving" @click="updateOpen(false)">关闭</Button>
          <Button size="sm" :disabled="validating || saving || statusLoading || !!statusError" @click="saveToStore">{{ saving ? '保存中…' : '保存设置' }}</Button>
        </div>
      </footer>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
:global(.settings-dialog) {
  width: min(960px, calc(100vw - 40px)); max-width: none;
  height: min(660px, calc(100dvh - 48px));
  display: flex; flex-direction: column; gap: 0; padding: 0; overflow: hidden;
  border-radius: 18px;
}
.settings-header { flex: none; padding: 20px 28px 16px; border-bottom: 1px solid hsl(var(--border)); text-align: left; }
.settings-status { display: flex; align-items: center; gap: 6px; min-height: 18px; font-size: 12px; color: hsl(var(--muted-foreground)); }
.settings-body { position: relative; display: grid; grid-template-columns: 174px minmax(0, 1fr); flex: 1; min-height: 0; }
.settings-nav { display: flex; flex-direction: column; gap: 5px; padding: 20px 12px; border-right: 1px solid hsl(var(--border)); background: hsl(var(--muted) / .35); }
.settings-nav button { display: flex; align-items: center; gap: 10px; padding: 11px 12px; border-radius: 9px; font-size: 13px; text-align: left; color: hsl(var(--muted-foreground)); }
.settings-nav button:hover, .settings-nav button.selected { color: hsl(var(--foreground)); background: hsl(var(--muted)); }
.settings-nav button.selected { font-weight: 600; }
.settings-content { grid-column: 2; grid-row: 1; min-height: 0; min-width: 0; padding: 20px 28px; overflow-y: auto; overscroll-behavior: contain; }
.settings-page-heading { margin-bottom: 14px; }
.settings-page-heading h3 { font-size: 18px; font-weight: 600; line-height: 1.4; }
.settings-page-heading p, .settings-hint { font-size: 12px; line-height: 1.65; color: hsl(var(--muted-foreground)); }
.settings-page-heading p { margin-top: 4px; }
.settings-section-intro { margin-bottom: 12px; }
.settings-toggle { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 13px; cursor: pointer; }
.settings-toggle input { width: 16px; height: 16px; accent-color: hsl(var(--foreground)); }
.settings-section-intro > .settings-hint { margin-top: 8px; }
.settings-role-picker { display: flex; gap: 4px; margin-top: 14px; padding: 3px; border-radius: 9px; background: hsl(var(--muted) / .65); }
.settings-role-picker button { flex: 1; border-radius: 6px; padding: 6px 8px; font-size: 12px; color: hsl(var(--muted-foreground)); }
.settings-role-picker button[aria-pressed="true"] { background: hsl(var(--background)); color: hsl(var(--foreground)); box-shadow: 0 1px 3px #00000010; }
.settings-connection-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.settings-connection-heading h4 { font-size: 13px; font-weight: 600; }
.settings-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; }
.settings-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.settings-field label { font-size: 12px; color: hsl(var(--muted-foreground)); }
.settings-field :deep(input), .settings-field :deep(button[role="combobox"]) { height: 34px; border-radius: 8px; font-size: 13px; }
.settings-connection > .settings-hint { margin-top: 10px; }
.settings-connection-actions { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
.settings-text-button { font-size: 12px; color: hsl(var(--muted-foreground)); }
.settings-text-button:hover, .settings-literature a { color: hsl(var(--foreground)); text-decoration: underline; text-underline-offset: 3px; }
.settings-empty { margin-top: 24px; padding: 24px; border: 1px dashed hsl(var(--border)); border-radius: 10px; font-size: 13px; color: hsl(var(--muted-foreground)); }
.settings-note { margin-top: 14px; }
.settings-literature { display: grid; justify-items: start; gap: 16px; }
.settings-literature .settings-field { width: 100%; }
.settings-capabilities { min-width: 0; }
.settings-footer { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 24px; border-top: 1px solid hsl(var(--border)); }
.settings-footer-status { min-width: 0; font-size: 11px; line-height: 1.5; color: hsl(var(--muted-foreground)); }
.settings-footer-actions { display: flex; flex-shrink: 0; gap: 8px; }
.settings-error { display: flex; align-items: center; gap: 6px; color: hsl(var(--destructive)); }
.settings-error button { flex-shrink: 0; text-decoration: underline; }
.settings-mobile-nav { display: none; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid hsl(var(--ring)); outline-offset: 2px; }
@media (max-width: 640px) {
  :global(.settings-dialog) { width: calc(100vw - 20px); height: calc(100dvh - 24px); border-radius: 14px; }
  .settings-header { padding: 18px 20px 12px; }
  .settings-body { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
  .settings-nav { display: none; }
  .settings-mobile-nav { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px; border-bottom: 1px solid hsl(var(--border)); font-size: 12px; }
  .settings-mobile-nav select { min-width: 150px; padding: 7px 10px; border: 1px solid hsl(var(--border)); border-radius: 8px; background: hsl(var(--background)); }
  .settings-content { grid-column: 1; grid-row: 2; padding: 18px 20px; }
  .settings-form-grid { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .settings-footer { padding: 12px 16px; flex-wrap: wrap; }
  .settings-footer-actions { margin-left: auto; }
  .settings-connection-heading { flex-wrap: wrap; gap: 4px; }
}
</style>
