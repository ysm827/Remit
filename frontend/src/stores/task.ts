import {
	type TaskSummary,
	cancelTask as cancelTaskAPI,
	clearTaskHistory as clearTaskHistoryAPI,
	deleteTask as deleteTaskAPI,
	getPendingApproval,
	getTaskHistory,
	getTaskMessages,
	getTaskWorkspace,
	requestTaskCopilot,
	resumeTask as resumeTaskAPI,
	sendTaskMessage as sendTaskMessageAPI,
	submitApproval as submitApprovalAPI,
} from "@/apis/commonApi";
import type { CopilotAction } from "@/apis/commonApi";
import { AgentType } from "@/utils/enum";
import type {
	ActivityMessage,
	ApprovalMessage,
	CoderMessage,
	CoordinatorMessage,
	ExecutionSummaryMessage,
	InterpreterMessage,
	Message,
	ModelerMessage,
	ProgressMessage,
	TaskStatus,
	TaskWorkspaceSnapshot,
	WriterMessage,
} from "@/utils/response";
import { TaskWebSocket } from "@/utils/websocket";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

type ConnectionState =
	| "connecting"
	| "connected"
	| "disconnected"
	| "reconnecting";

function websocketBaseUrl(): string {
	const configured = import.meta.env.VITE_WS_URL?.trim();
	if (configured) return configured.replace(/\/$/, "");
	const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
	return `${protocol}//${window.location.host}`;
}

/** 后端目前会推送的消息大类 */
const KNOWN_MSG_TYPES = new Set([
	"system",
	"agent",
	"user",
	"tool",
	"approval",
	"execution_summary",
	"progress",
	"activity",
]);

/** 当前任务的持久化键（用于刷新后恢复选中态） */
const CURRENT_TASK_STORAGE_KEY = "currentTaskId";

/** 类型守卫：判断是否为有效的消息对象 */
function isMessagePayload(payload: unknown): payload is Message {
	if (payload === null || typeof payload !== "object") {
		return false;
	}
	const id = Reflect.get(payload, "id");
	const msgType = Reflect.get(payload, "msg_type");
	return (
		typeof id === "string" &&
		typeof msgType === "string" &&
		KNOWN_MSG_TYPES.has(msgType)
	);
}

function isApprovalMessage(message: Message): message is ApprovalMessage {
	return message.msg_type === "approval";
}

function isInterpreterMessage(message: Message): message is InterpreterMessage {
	return (
		message.msg_type === "tool" &&
		"tool_name" in message &&
		message.tool_name === "execute_code"
	);
}

/** 只有整个任务的完成/停止/失败消息才是终态。 */
function isTerminalTaskMessage(message: Message): boolean {
	if (message.task_status) {
		return ["completed", "failed", "stopped"].includes(message.task_status);
	}
	if (message.msg_type !== "system") {
		return false;
	}
	const content = message.content ?? "";
	if (message.type === "success") {
		return content === "任务处理完成";
	}
	if (message.type === "error") {
		return content.startsWith("任务执行失败");
	}
	if (message.type === "warning") {
		return content.includes("任务已停止") || content.includes("服务重启");
	}
	return false;
}

function isTaskStartMessage(message: Message): boolean {
	if (message.task_status) return message.task_status === "running";
	if (message.msg_type !== "system") {
		return false;
	}
	const content = message.content ?? "";
	return (
		content === "任务开始处理" ||
		content.startsWith("任务从节点 ") ||
		content.startsWith("任务继续处理")
	);
}

/** 优先消费线协议状态；仅为历史消息保留中文文案兼容。 */
function taskStatusOf(message: Message): TaskStatus | null {
	if (message.task_status) return message.task_status;
	if (isApprovalMessage(message)) return "awaiting_approval";
	if (isTaskStartMessage(message)) return "running";
	if (!isTerminalTaskMessage(message) || message.msg_type !== "system")
		return null;
	if (message.type === "success") return "completed";
	return message.type === "error" ? "failed" : "stopped";
}

/** 解析消息时间戳；缺失或非法时返回 null */
function parseTimestamp(message: Message): number | null {
	if (!message.created_at) {
		return null;
	}
	const ts = Date.parse(message.created_at);
	return Number.isNaN(ts) ? null : ts;
}

/** 按时间戳升序排列；无法解析时间戳的消息保持相对顺序 */
function orderByTimestamp(items: Message[]): Message[] {
	return [...items].sort((a, b) => {
		if (a.sequence != null && b.sequence != null) {
			return a.sequence - b.sequence;
		}
		const ta = parseTimestamp(a);
		const tb = parseTimestamp(b);
		if (ta === null || tb === null) {
			return 0;
		}
		return ta - tb;
	});
}

/** 固定 ID 的进度消息也会重放；旧版本不能覆盖已经收到的新版。 */
function isOlderOrSameMessage(incoming: Message, existing: Message): boolean {
	if (existing.sequence != null && incoming.sequence == null) return true;
	if (incoming.sequence != null && existing.sequence != null) {
		return incoming.sequence <= existing.sequence;
	}
	const incomingTime = parseTimestamp(incoming);
	const existingTime = parseTimestamp(existing);
	if (
		incomingTime !== null &&
		existingTime !== null &&
		incomingTime < existingTime
	)
		return true;
	return JSON.stringify(incoming) === JSON.stringify(existing);
}

/** 播放短促提示音；失败时静默降级 */
function playAttentionSound(): void {
	try {
		const Ctor =
			window.AudioContext ??
			(window as unknown as { webkitAudioContext?: typeof AudioContext })
				.webkitAudioContext;
		if (!Ctor) {
			return;
		}
		const ctx = new Ctor();
		const osc = ctx.createOscillator();
		const gain = ctx.createGain();
		osc.frequency.value = 880;
		gain.gain.setValueAtTime(0.08, ctx.currentTime);
		gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
		osc.connect(gain);
		gain.connect(ctx.destination);
		osc.onended = () => void ctx.close();
		osc.start();
		osc.stop(ctx.currentTime + 0.5);
	} catch {
		// 声音提示失败不影响功能
	}
}

/** 需要人工出手时主动提醒：声音 + 桌面通知。 */
function notifyUser(title: string, body: string): void {
	playAttentionSound();
	try {
		if (typeof Notification === "undefined") {
			return;
		}
		if (Notification.permission === "granted") {
			new Notification(title, { body: body.slice(0, 120) });
		}
	} catch {
		// 桌面通知失败不影响功能
	}
}

/** 任务管理 Store */
export const useTaskStore = defineStore("task", () => {
	// ---- State ----

	/** 按任务ID分组的消息记录 */
	const messagesByTask = ref<Record<string, Message[]>>({});

	/** 当前活跃的任务ID */
	const currentTaskId = ref<string | null>(null);

	/** 后端持久化的任务历史索引 */
	const taskHistory = ref<TaskSummary[]>([]);

	/** 已处理的消息ID集合（用于去重） */
	const seenMessageIdsByTask = new Map<string, Set<string>>();

	/** WebSocket 实例 */
	let socket: TaskWebSocket | null = null;
	/** 切换项目、离开页面后，旧连接和旧请求的回调都必须失效。 */
	let connectionEpoch = 0;
	const messageLoads = new Map<string, number>();
	const approvalLoads = new Map<string, number>();
	const workspaceLoads = new Map<string, number>();
	const workspaceReadVersions = new Map<string, number>();
	const stateRevisions = new Map<string, number>();
	const liveMessageVersions = new Map<string, Map<string, number>>();
	let liveVersion = 0;
	let historyLoadVersion = 0;
	let workspaceRefreshTimer: ReturnType<typeof setTimeout> | null = null;

	/** WebSocket 连接状态 */
	const wsStatus = ref<ConnectionState>("disconnected");

	/** 任务历史列表最近一次加载是否失败（区别于空列表）。 */
	const taskHistoryLoadError = ref(false);

	/** 任务是否正在运行 */
	const taskStatuses = ref<Record<string, TaskStatus>>({});
	const isRunning = computed(() =>
		currentTaskId.value
			? taskStatuses.value[currentTaskId.value] === "running"
			: false,
	);

	/** 每个任务当前唯一有效的待审核节点。 */
	const pendingApprovalsByTask = ref<Record<string, ApprovalMessage | null>>(
		{},
	);

	/** 主页面直接消费的工作流产物快照，不能从 Copilot 消息反推。 */
	const workspaceSnapshotsByTask = ref<
		Record<string, TaskWorkspaceSnapshot | null>
	>({});

	/** 候选否决等操作预填的退回意见草稿，打开返修对话框时消费。 */
	const reviseDraft = ref("");

	// ---- 基础派生态 ----

	/** 当前任务的消息列表 */
	const messages = computed<Message[]>(() =>
		currentTaskId.value
			? (messagesByTask.value[currentTaskId.value] ?? [])
			: [],
	);

	const pendingApproval = computed<ApprovalMessage | null>(() =>
		currentTaskId.value
			? (pendingApprovalsByTask.value[currentTaskId.value] ?? null)
			: null,
	);

	const workspaceSnapshot = computed<TaskWorkspaceSnapshot | null>(() =>
		currentTaskId.value
			? (workspaceSnapshotsByTask.value[currentTaskId.value] ?? null)
			: null,
	);

	// ---- 消息桶维护 ----

	function nextVersion(versions: Map<string, number>, taskId: string): number {
		const version = (versions.get(taskId) ?? 0) + 1;
		versions.set(taskId, version);
		return version;
	}

	function isActiveSession(taskId: string, epoch: number): boolean {
		return currentTaskId.value === taskId && connectionEpoch === epoch;
	}

	function latestStateMessage(taskId: string): Message | undefined {
		return [...(messagesByTask.value[taskId] ?? [])]
			.reverse()
			.find((message) => taskStatusOf(message) !== null);
	}

	/** 设置当前活跃任务 */
	function setCurrentTask(taskId: string): void {
		if (currentTaskId.value !== taskId) reviseDraft.value = "";
		currentTaskId.value = taskId;
		if (typeof window !== "undefined") {
			window.localStorage.setItem(CURRENT_TASK_STORAGE_KEY, taskId);
		}
	}

	function clearCurrentTaskSelection(): void {
		currentTaskId.value = null;
		if (
			typeof window !== "undefined" &&
			window.localStorage.getItem(CURRENT_TASK_STORAGE_KEY)
		) {
			window.localStorage.removeItem(CURRENT_TASK_STORAGE_KEY);
		}
	}

	/** 确保任务的消息桶存在 */
	function ensureTaskBucket(taskId: string): void {
		messagesByTask.value[taskId] ??= [];
		seenMessageIdsByTask.set(
			taskId,
			seenMessageIdsByTask.get(taskId) ?? new Set(),
		);
	}

	/** 追加消息；同 ID 视为更新（WebSocket 回显与 REST 返回可能重复） */
	function appendMessage(taskId: string, message: Message): boolean {
		ensureTaskBucket(taskId);
		const bucket = messagesByTask.value[taskId];
		const seen = seenMessageIdsByTask.get(taskId);

		if (message.id && seen?.has(message.id)) {
			const index = bucket.findIndex((existing) => existing.id === message.id);
			if (index >= 0) {
				if (isOlderOrSameMessage(message, bucket[index])) return false;
				bucket[index] = message;
			}
			messagesByTask.value[taskId] = orderByTimestamp(bucket);
			return true;
		}
		if (message.id) {
			seen?.add(message.id);
		}
		messagesByTask.value[taskId] = orderByTimestamp([...bucket, message]);
		return true;
	}

	/** 合并历史消息（用于加载历史记录） */
	function mergeMessages(
		taskId: string,
		incoming: Message[],
		startedAt: number,
	): void {
		ensureTaskBucket(taskId);
		const byId = new Map(
			messagesByTask.value[taskId].map((message) => [message.id, message]),
		);
		for (const message of incoming) {
			// 旧后端没有 sequence 时，发起请求后收到的实时内容优先于该快照。
			const changedDuringLoad =
				(liveMessageVersions.get(taskId)?.get(message.id) ?? 0) > startedAt;
			if (changedDuringLoad && message.sequence == null) continue;
			const existing = byId.get(message.id);
			if (!existing || !isOlderOrSameMessage(message, existing))
				byId.set(message.id, message);
		}
		messagesByTask.value[taskId] = orderByTimestamp([...byId.values()]);
		seenMessageIdsByTask.set(taskId, new Set(byId.keys()));
	}

	/** 依据当前消息流重算“是否运行中”（从尾部向前找最近的状态事件） */
	function syncRunningState(taskId: string): void {
		if (currentTaskId.value !== taskId) {
			return;
		}
		const lastSignal = latestStateMessage(taskId);
		const status = lastSignal ? taskStatusOf(lastSignal) : null;
		if (status) taskStatuses.value[taskId] = status;
	}

	// ---- 实时通道 ----

	/** 连接 WebSocket 接收实时消息 */
	function connectWebSocket(taskId: string): void {
		closeWebSocket();
		setCurrentTask(taskId);
		ensureTaskBucket(taskId);
		syncRunningState(taskId);
		const epoch = connectionEpoch;

		const url = `${websocketBaseUrl()}/task/${encodeURIComponent(taskId)}`;

		const handlePayload = (data: unknown) => {
			if (!isActiveSession(taskId, epoch)) return;
			if (!isMessagePayload(data)) {
				console.warn("忽略非标准任务消息:", data);
				return;
			}
			if (!appendMessage(taskId, data)) return;
			const versions =
				liveMessageVersions.get(taskId) ?? new Map<string, number>();
			versions.set(data.id, ++liveVersion);
			liveMessageVersions.set(taskId, versions);
			if (data.msg_type === "progress" || data.msg_type === "approval") {
				scheduleWorkspaceRefresh(taskId);
			}
			// 服务端可能重放较早的审批/启动事件，只有最新生命周期事件能改当前状态。
			const status = taskStatusOf(data);
			if (!status || latestStateMessage(taskId)?.id !== data.id) return;
			nextVersion(stateRevisions, taskId);
			nextVersion(approvalLoads, taskId);
			taskStatuses.value[taskId] = status;
			taskHistory.value = taskHistory.value.map((task) =>
				task.task_id === taskId ? { ...task, status } : task,
			);
			if (isApprovalMessage(data)) {
				pendingApprovalsByTask.value[taskId] = data;
				notifyUser(`等待你的审核：${data.node_label}`, data.summary);
				void loadTaskHistory();
				return;
			}
			if (isTerminalTaskMessage(data)) {
				pendingApprovalsByTask.value[taskId] = null;
				scheduleWorkspaceRefresh(taskId);
				if (data.msg_type === "system" && data.type === "error") {
					notifyUser("任务需要你处理", data.content ?? "任务执行失败");
				}
				void loadTaskHistory();
				return;
			}
			if (isTaskStartMessage(data)) {
				// 任务重新跑起来说明审批已被处理（可能在别处批准），清掉残留横幅
				pendingApprovalsByTask.value[taskId] = null;
				scheduleWorkspaceRefresh(taskId);
				void loadTaskHistory();
			}
		};

		socket = new TaskWebSocket(url, handlePayload, (status) => {
			if (!isActiveSession(taskId, epoch)) return;
			wsStatus.value = status;
			// 先建立通道再补历史，覆盖首次进入与断线期间遗漏的事件。
			if (status === "connected") {
				void loadTaskMessages(taskId);
				void loadTaskHistory();
			}
		});
		socket.connect();
	}

	/** 关闭 WebSocket 连接 */
	function closeWebSocket(taskId?: string): void {
		if (taskId && currentTaskId.value !== taskId) return;
		connectionEpoch += 1;
		if (workspaceRefreshTimer !== null) {
			clearTimeout(workspaceRefreshTimer);
			workspaceRefreshTimer = null;
		}
		if (socket) {
			socket.close();
			socket = null;
		}
		wsStatus.value = "disconnected";
	}

	function scheduleWorkspaceRefresh(taskId: string): void {
		if (workspaceRefreshTimer !== null) clearTimeout(workspaceRefreshTimer);
		// 重放会密集推送多个节点；合并刷新，避免为每条旧进度发起一次请求。
		nextVersion(workspaceLoads, taskId);
		const epoch = connectionEpoch;
		workspaceRefreshTimer = setTimeout(() => {
			workspaceRefreshTimer = null;
			if (isActiveSession(taskId, epoch)) void loadTaskWorkspace(taskId);
		}, 100);
	}

	// ---- 数据加载 ----

	/** 加载任务的历史消息 */
	async function loadTaskMessages(taskId: string): Promise<void> {
		if (currentTaskId.value !== taskId) return;
		const epoch = connectionEpoch;
		const version = nextVersion(messageLoads, taskId);
		const startedAt = liveVersion;
		ensureTaskBucket(taskId);
		try {
			const response = await getTaskMessages(taskId);
			if (
				!isActiveSession(taskId, epoch) ||
				messageLoads.get(taskId) !== version
			)
				return;
			mergeMessages(
				taskId,
				(response.data ?? []).filter(isMessagePayload),
				startedAt,
			);
			syncRunningState(taskId);
			await Promise.all([
				loadPendingApproval(taskId),
				loadTaskWorkspace(taskId),
			]);
		} catch (error) {
			console.error("加载任务历史消息失败:", error);
		}
	}

	/** 加载冻结产物；失败返回 null，被更新请求取代时返回 undefined。 */
	async function loadTaskWorkspace(taskId: string) {
		if (currentTaskId.value !== taskId) return undefined;
		const epoch = connectionEpoch;
		const version = nextVersion(workspaceLoads, taskId);
		const startedAt = liveVersion;
		const isCurrent = () =>
			isActiveSession(taskId, epoch) && workspaceLoads.get(taskId) === version;
		try {
			const response = await getTaskWorkspace(taskId);
			if (!isCurrent()) return undefined;
			workspaceReadVersions.set(taskId, startedAt);
			workspaceSnapshotsByTask.value[taskId] = response.data;
			return response.data;
		} catch (error) {
			if (!isCurrent()) return undefined;
			console.error("加载项目阶段产物失败:", error);
			// 短暂失败保留最后一次有效快照，旧请求也不能清空后来成功的结果。
			return null;
		}
	}

	/** 从检查点恢复当前待审核节点，不能只依赖实时消息。 */
	async function loadPendingApproval(taskId: string): Promise<void> {
		if (currentTaskId.value !== taskId) return;
		const epoch = connectionEpoch;
		const version = nextVersion(approvalLoads, taskId);
		try {
			const response = await getPendingApproval(taskId);
			if (
				!isActiveSession(taskId, epoch) ||
				approvalLoads.get(taskId) !== version
			)
				return;
			const pending = response.data.pending;
			pendingApprovalsByTask.value[taskId] = pending
				? {
						...pending,
						id: pending.checkpoint_id,
						msg_type: "approval",
						content: `“${pending.node_label}”已生成结果，等待你的审核`,
						options: ["approve", "revise"],
					}
				: null;
			if (pending) taskStatuses.value[taskId] = "awaiting_approval";
			else if (
				[
					"running",
					"awaiting_approval",
					"completed",
					"failed",
					"stopped",
				].includes(response.data.status)
			)
				taskStatuses.value[taskId] = response.data.status as TaskStatus;
		} catch (error) {
			console.error("加载人工审核状态失败:", error);
		}
	}

	/** 加载可跨刷新、跨后端重启恢复的任务列表 */
	async function loadTaskHistory(): Promise<void> {
		const version = ++historyLoadVersion;
		try {
			const response = await getTaskHistory();
			if (version !== historyLoadVersion) return;
			taskHistory.value = response.data ?? [];
			taskHistoryLoadError.value = false;
		} catch (error) {
			if (version !== historyLoadVersion) return;
			// 首页必须区分"没有项目"和"加载失败"，否则后端抖动会被当成数据被清空。
			taskHistoryLoadError.value = true;
			console.error("加载任务历史失败:", error);
		}
	}

	// ---- 任务生命周期操作 ----

	/** 永久删除历史任务，并同步清理本地缓存。 */
	async function deleteTask(taskId: string) {
		const response = await deleteTaskAPI(taskId);
		historyLoadVersion += 1;
		taskHistory.value = taskHistory.value.filter((t) => t.task_id !== taskId);
		delete messagesByTask.value[taskId];
		delete pendingApprovalsByTask.value[taskId];
		delete workspaceSnapshotsByTask.value[taskId];
		seenMessageIdsByTask.delete(taskId);
		liveMessageVersions.delete(taskId);
		workspaceReadVersions.delete(taskId);
		delete taskStatuses.value[taskId];

		if (currentTaskId.value === taskId) {
			closeWebSocket();
			clearCurrentTaskSelection();
		}
		return response.data;
	}

	/** 永久清空全部历史任务，并同步清理当前选择和本地缓存。 */
	async function clearTaskHistory() {
		const response = await clearTaskHistoryAPI();
		historyLoadVersion += 1;
		closeWebSocket();
		taskHistory.value = [];
		messagesByTask.value = {};
		pendingApprovalsByTask.value = {};
		workspaceSnapshotsByTask.value = {};
		seenMessageIdsByTask.clear();
		liveMessageVersions.clear();
		workspaceReadVersions.clear();
		taskStatuses.value = {};
		clearCurrentTaskSelection();
		return response.data;
	}

	/** 保存用户补充消息；成功后立即合并，WebSocket 回显会按 ID 去重。 */
	async function sendUserMessage(taskId: string, content: string) {
		const text = content.trim();
		if (!text) {
			return null;
		}
		const response = await sendTaskMessageAPI(taskId, text);
		if (isMessagePayload(response.data)) {
			appendMessage(taskId, response.data);
		}
		await loadTaskHistory();
		return response.data;
	}

	/** 主动请求建模手解释冻结证据；与普通“补充消息”语义分离。 */
	async function requestCopilot(taskId: string, action: CopilotAction) {
		const response = await requestTaskCopilot(taskId, action);
		for (const payload of [response.data.request, response.data.response]) {
			if (isMessagePayload(payload)) {
				appendMessage(taskId, payload);
			}
		}
		await loadTaskHistory();
		return response.data;
	}

	/** 取消正在运行的任务 */
	async function stopTask(taskId: string) {
		const epoch = connectionEpoch;
		const revision = stateRevisions.get(taskId);
		try {
			const { data } = await cancelTaskAPI(taskId);
			if (data.success) {
				if (
					isActiveSession(taskId, epoch) &&
					stateRevisions.get(taskId) === revision
				) {
					taskStatuses.value[taskId] = "stopped";
					nextVersion(approvalLoads, taskId);
				}
				await loadTaskHistory();
			} else {
				await loadTaskMessages(taskId);
			}
			return data;
		} catch (cause) {
			console.error("无法取消当前任务", cause);
			return { success: false, message: "取消服务暂时不可用" };
		}
	}

	/** 从用户选择的持久化节点继续运行原任务。 */
	async function resumeTask(taskId: string, nodeId: string) {
		const epoch = connectionEpoch;
		const revision = stateRevisions.get(taskId);
		const response = await resumeTaskAPI(taskId, nodeId);
		if (response.data.success) {
			markTaskRunning(taskId, epoch, revision);
		}
		return response.data;
	}

	/** 提交人工审核决定；只有后端成功持久化后才移除审阅台。 */
	async function decideApproval(
		taskId: string,
		decision: "approve" | "revise",
		feedback = "",
		targetNodeId?: string,
	) {
		const epoch = connectionEpoch;
		const revision = stateRevisions.get(taskId);
		const approval = pendingApprovalsByTask.value[taskId];
		if (!approval) {
			throw new Error("当前没有待审核节点");
		}
		const response = await submitApprovalAPI(taskId, {
			checkpoint_id: approval.checkpoint_id,
			decision,
			feedback,
			target_node_id: targetNodeId,
		});
		if (!response.data.success) throw new Error(response.data.message);
		markTaskRunning(taskId, epoch, revision);
		return response.data;
	}

	/** 保留已建立的实时通道；迟到的操作响应不能抢回别的项目或覆盖下一次审批。 */
	function markTaskRunning(
		taskId: string,
		epoch: number,
		revision: number | undefined,
	): void {
		if (!isActiveSession(taskId, epoch)) return;
		if (stateRevisions.get(taskId) === revision) {
			taskStatuses.value[taskId] = "running";
			pendingApprovalsByTask.value[taskId] = null;
			nextVersion(approvalLoads, taskId);
			scheduleWorkspaceRefresh(taskId);
		}
		taskHistory.value = taskHistory.value.map((t) =>
			t.task_id === taskId ? { ...t, status: taskStatuses.value[taskId] } : t,
		);
		void loadTaskHistory();
	}

	/** 下载消息为 JSON 文件 */
	function downloadMessages(): void {
		const href = `data:text/json;charset=utf-8,${encodeURIComponent(JSON.stringify(messages.value, null, 2))}`;
		const anchor = document.createElement("a");
		anchor.href = href;
		anchor.download = `${currentTaskId.value ?? "task"}-messages.json`;
		document.body.appendChild(anchor);
		anchor.click();
		anchor.remove();
	}

	// ---- 展示层派生态 ----

	/** Copilot 时间线展示所有 Agent 回复、用户补充和系统事件。 */
	const chatMessages = computed(() =>
		messages.value.filter((msg) => {
			switch (msg.msg_type) {
				case "agent":
					return msg.content != null && msg.content !== "";
				case "user":
				case "system":
					return true;
				default:
					return false;
			}
		}),
	);

	/** 按角色过滤 Agent 消息 */
	function agentMessagesOf<T extends Message>(agentType: AgentType) {
		return computed(() =>
			messages.value.filter(
				(msg): msg is T =>
					msg.msg_type === "agent" &&
					msg.agent_type === agentType &&
					msg.content != null,
			),
		);
	}

	/** 协调者消息列表 */
	const coordinatorMessages = agentMessagesOf<CoordinatorMessage>(
		AgentType.COORDINATOR,
	);
	/** 建模者消息列表 */
	const modelerMessages = agentMessagesOf<ModelerMessage>(AgentType.MODELER);
	/** 代码手消息列表 */
	const coderMessages = agentMessagesOf<CoderMessage>(AgentType.CODER);
	/** 论文手消息列表 */
	const writerMessages = agentMessagesOf<WriterMessage>(AgentType.WRITER);

	/** 代码执行工具消息列表 */
	const interpreterMessage = computed(() =>
		messages.value.filter(isInterpreterMessage),
	);

	/** 每个求解节点的紧凑运行记录，不再从代码输出文本中猜测结论。 */
	const executionSummaries = computed(() =>
		messages.value.filter(
			(msg): msg is ExecutionSummaryMessage =>
				msg.msg_type === "execution_summary",
		),
	);

	/** 从尾部取最近一条满足条件的消息 */
	function lastMessageOfType<T extends Message>(msgType: string) {
		return computed<T | null>(() => {
			const hit = [...messages.value]
				.reverse()
				.find((m) => m.msg_type === msgType);
			return (hit as T | undefined) ?? null;
		});
	}

	const lastProgressMessage = lastMessageOfType<ProgressMessage>("progress");
	/** 实时进度与工作区快照各有刷新节奏，显示有更新证据的一份。 */
	const latestProgress = computed<ProgressMessage | null>(() => {
		const snapshot = workspaceSnapshot.value?.progress;
		const message = lastProgressMessage.value;
		if (!snapshot) return message;
		if (!message) return snapshot;
		if (snapshot.sequence != null && message.sequence != null) {
			return message.sequence > snapshot.sequence ? message : snapshot;
		}
		const snapshotTime = parseTimestamp(snapshot);
		const messageTime = parseTimestamp(message);
		if (
			snapshotTime !== null &&
			messageTime !== null &&
			snapshotTime !== messageTime
		) {
			return messageTime > snapshotTime ? message : snapshot;
		}
		// 旧响应无时间/序号时，用请求开始时已见的实时版本判断：
		// 请求期间或之后到达的消息优先，否则采用更新读取的权威快照。
		const taskId = currentTaskId.value;
		if (!taskId) return message;
		const receivedAt = liveMessageVersions.get(taskId)?.get(message.id) ?? 0;
		return receivedAt > (workspaceReadVersions.get(taskId) ?? -1)
			? message
			: snapshot;
	});

	/** 最新的实时活动播报（不落盘，只在任务运行时出现）。 */
	const latestActivity = lastMessageOfType<ActivityMessage>("activity");

	/** 从最新代码手消息中提取文件列表 */
	const files = computed<string[]>(() => {
		const hit = [...coderMessages.value]
			.reverse()
			.find(
				(msg) =>
					"files" in msg && Array.isArray(msg.files) && msg.files.length > 0,
			);
		if (hit && "files" in hit && Array.isArray(hit.files)) {
			return hit.files as string[];
		}
		return [];
	});

	return {
		messages,
		taskHistory,
		wsStatus,
		isRunning,
		pendingApproval,
		workspaceSnapshot,
		chatMessages,
		coordinatorMessages,
		modelerMessages,
		coderMessages,
		writerMessages,
		interpreterMessage,
		executionSummaries,
		latestProgress,
		latestActivity,
		reviseDraft,
		files,
		loadTaskMessages,
		loadPendingApproval,
		loadTaskWorkspace,
		loadTaskHistory,
		taskHistoryLoadError,
		deleteTask,
		clearTaskHistory,
		sendUserMessage,
		requestCopilot,
		connectWebSocket,
		closeWebSocket,
		stopTask,
		resumeTask,
		decideApproval,
		downloadMessages,
	};
});
