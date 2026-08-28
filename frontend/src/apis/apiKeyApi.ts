import request from "@/utils/request";

export type AgentCredentials = {
	apiKey: string;
	baseUrl: string;
	modelId: string;
	apiType: string;
};

export type ValidateApiKeyRequest = {
	api_key: string;
	model_id: string;
	base_url?: string;
	api_type?: string;
};

type ValidationResponse = {
	valid: boolean;
	message: string;
};
export type ValidateApiKeyResponse = ValidationResponse;

/** 后端实际生效的单个 Agent 配置元数据（永不包含密钥） */
export type AgentApiConfigStatus = {
	configured: boolean;
	api_key_configured: boolean;
	context_window: number;
	source: "environment" | "runtime" | "missing";
	api_type: string | null;
	model_id: string | null;
	base_url: string | null;
};

/** 全部 Agent 的配置状态 */
export type ApiConfigStatusResponse = {
	configured: boolean;
	model_council_enabled: boolean;
	agents: Readonly<Record<string, AgentApiConfigStatus>>;
};

/** 保存 API 配置请求参数 */
type CoreRoleConfig = {
	coordinator: AgentCredentials;
	modeler: AgentCredentials;
	coder: AgentCredentials;
	writer: AgentCredentials;
};

export type SaveApiConfigRequest = CoreRoleConfig & {
	openalex_email: string;
	model_scout?: AgentCredentials;
	model_critic?: AgentCredentials;
	model_council_enabled?: boolean;
};

/** 验证 OpenAlex Email 请求 / 响应 */
export type ValidateOpenalexEmailRequest = { email: string };
export type ValidateOpenalexEmailResponse = ValidationResponse;

const CONFIG_ENDPOINTS = {
	validateModel: "/validate-api-key",
	status: "/api-config-status",
	validateOpenAlex: "/validate-openalex-email",
	save: "/save-api-config",
} as const;

/** 验证一组模型接入参数是否可用 */
export function validateApiKey(params: ValidateApiKeyRequest) {
	return request.post<ValidateApiKeyResponse>(
		CONFIG_ENDPOINTS.validateModel,
		params,
		{
			// 后端会在 45 秒时返回结构化的供应商超时；这里留出传输余量。
			timeout: 60_000,
		},
	);
}

/** 查询后端各 Agent 的配置来源与完整度 */
export function getApiConfigStatus() {
	return request.get<ApiConfigStatusResponse>(CONFIG_ENDPOINTS.status);
}

/** 校验 OpenAlex 联系邮箱 */
export function validateOpenalexEmail(params: ValidateOpenalexEmailRequest) {
	return request.post<ValidateOpenalexEmailResponse>(
		CONFIG_ENDPOINTS.validateOpenAlex,
		params,
	);
}

/** 把界面填写的模型接入配置写入后端运行时 */
export function saveApiConfig(params: SaveApiConfigRequest) {
	return request.post<{ success: boolean; message: string }>(
		CONFIG_ENDPOINTS.save,
		params,
	);
}
