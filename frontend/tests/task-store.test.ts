import { useTaskStore } from "@/stores/task";
import type {
	ApprovalMessage,
	Message,
	ProgressMessage,
} from "@/utils/response";
import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
	getTaskMessages: vi.fn(),
	getPendingApproval: vi.fn(),
	getTaskWorkspace: vi.fn(),
	getTaskHistory: vi.fn(),
	submitApproval: vi.fn(),
	resumeTask: vi.fn(),
	cancelTask: vi.fn(),
	deleteTask: vi.fn(),
	clearTaskHistory: vi.fn(),
	requestTaskCopilot: vi.fn(),
	sendTaskMessage: vi.fn(),
}));

type SocketCallbacks = {
	url: string;
	message: (message: unknown) => void;
	status: (status: "connected" | "connecting" | "disconnected") => void;
};
const sockets = vi.hoisted(() => [] as SocketCallbacks[]);
vi.mock("@/apis/commonApi", () => api);
vi.mock("@/utils/websocket", () => ({
	TaskWebSocket: class {
		constructor(
			readonly url: string,
			readonly message: SocketCallbacks["message"],
			readonly status: SocketCallbacks["status"],
		) {
			sockets.push(this);
		}
		connect() {
			this.status("connecting");
		}
		close() {
			this.status("disconnected");
		}
	},
}));

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => {
		resolve = done;
	});
	return { promise, resolve };
}

function approval(id = "checkpoint", sequence = 2): ApprovalMessage {
	return {
		id,
		checkpoint_id: id,
		msg_type: "approval",
		sequence,
		task_status: "awaiting_approval",
		node_id: "coordinator",
		node_label: "题目理解",
		summary: "请审核",
		artifacts: [],
		quality_report: {},
		revision_count: 0,
		revision_targets: [],
		options: ["approve", "revise"],
	};
}

function progress(sequence: number, percent: number): ProgressMessage {
	return {
		id: "progress:A",
		msg_type: "progress",
		sequence,
		percent,
		stages: [],
		current_node: "coordinator",
		completed_count: 0,
		total_count: 1,
		total_known: true,
	};
}

let store: ReturnType<typeof useTaskStore>;
beforeEach(() => {
	vi.resetAllMocks();
	vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
	sockets.length = 0;
	localStorage.clear();
	setActivePinia(createPinia());
	store = useTaskStore();
	api.getTaskMessages.mockResolvedValue({ data: [] });
	api.getPendingApproval.mockResolvedValue({
		data: { pending: null, status: "running" },
	});
	api.getTaskWorkspace.mockResolvedValue({ data: null });
	api.getTaskHistory.mockResolvedValue({ data: [] });
});
afterEach(() => {
	store.closeWebSocket();
	vi.useRealTimers();
});

describe("任务实时同步", () => {
	it("sequence 为 null 的实时活动仍能按固定 ID 连续更新", () => {
		store.connectWebSocket("A");
		const event = {
			id: "activity:A",
			msg_type: "activity",
			category: "llm",
			sequence: null,
			task_status: null,
		};
		sockets[0].message({ ...event, detail: "first" });
		sockets[0].message({ ...event, detail: "second" });
		expect(store.latestActivity?.detail).toBe("second");
		expect(store.messages).toHaveLength(1);
	});

	it("每次连接成功都恢复遗漏的历史、审批和工作区", async () => {
		store.connectWebSocket("A");
		sockets[0].status("connected");
		await flushPromises();
		expect(store.isRunning).toBe(true);
		sockets[0].status("disconnected");
		api.getTaskMessages.mockResolvedValue({ data: [approval()] });
		api.getPendingApproval.mockResolvedValue({
			data: { pending: approval(), status: "awaiting_approval" },
		});
		api.getTaskWorkspace.mockResolvedValue({
			data: { task_id: "A", version: "new" },
		});
		sockets[0].status("connected");
		await flushPromises();
		expect(api.getTaskMessages).toHaveBeenCalledTimes(2);
		expect(store.pendingApproval?.checkpoint_id).toBe("checkpoint");
		expect(store.isRunning).toBe(false);
		expect(store.workspaceSnapshot).toMatchObject({
			task_id: "A",
			version: "new",
		});
		expect(store.wsStatus).toBe("connected");
	});

	it("较旧历史不能覆盖已收到的较新 sequence 进度", async () => {
		const history = deferred<{ data: Message[] }>();
		api.getTaskMessages.mockReturnValue(history.promise);
		store.connectWebSocket("A");
		sockets[0].status("connected");
		sockets[0].message(progress(12, 90));
		history.resolve({ data: [progress(10, 40)] });
		await flushPromises();
		expect(store.latestProgress?.percent).toBe(90);
		sockets[0].message(progress(9, 20));
		expect(store.latestProgress?.percent).toBe(90);
		expect(
			store.messages.filter((message) => message.id === "progress:A"),
		).toHaveLength(1);
	});

	it("旧后端无 sequence 时，也保留历史请求期间到达的实时更新", async () => {
		const history = deferred<{ data: Message[] }>();
		api.getTaskMessages.mockReturnValue(history.promise);
		store.connectWebSocket("A");
		sockets[0].status("connected");
		sockets[0].message({ ...progress(12, 90), sequence: undefined });
		history.resolve({ data: [{ ...progress(10, 40), sequence: undefined }] });
		await flushPromises();
		expect(store.latestProgress?.percent).toBe(90);
	});

	it("重放旧审批不会覆盖后面的运行状态或重新打开审批卡", () => {
		store.connectWebSocket("A");
		sockets[0].message({
			id: "running",
			sequence: 9,
			msg_type: "system",
			type: "info",
			task_status: "running",
			content: "custom",
		});
		sockets[0].message(approval("old", 2));
		expect(store.isRunning).toBe(true);
		expect(store.pendingApproval).toBeNull();
	});

	it("优先使用明确生命周期状态，同时兼容旧中文文案", () => {
		store.connectWebSocket("A");
		sockets[0].message({
			id: "old-start",
			msg_type: "system",
			type: "info",
			content: "任务开始处理",
		});
		expect(store.isRunning).toBe(true);
		sockets[0].message({
			id: "finish",
			msg_type: "system",
			type: "info",
			content: "renamed completion text",
			task_status: "completed",
		});
		expect(store.isRunning).toBe(false);
		sockets[0].message({
			id: "restart",
			msg_type: "system",
			type: "warning",
			content: "任务已停止",
			task_status: "running",
		});
		expect(store.isRunning).toBe(true);
	});

	it("实时审批到达后，迟到的旧审批快照不能清空它", async () => {
		const pending = deferred<{ data: { pending: null; status: string } }>();
		api.getPendingApproval.mockReturnValue(pending.promise);
		store.connectWebSocket("A");
		const loading = store.loadPendingApproval("A");
		sockets[0].message(approval("live"));
		pending.resolve({ data: { pending: null, status: "running" } });
		await loading;
		expect(store.pendingApproval?.checkpoint_id).toBe("live");
		expect(store.isRunning).toBe(false);
	});

	it("较晚返回的旧工作区快照不能覆盖新的快照", async () => {
		const old = deferred<{ data: { task_id: string; version: string } }>();
		api.getTaskWorkspace
			.mockReturnValueOnce(old.promise)
			.mockResolvedValueOnce({ data: { task_id: "A", version: "new" } });
		store.connectWebSocket("A");
		const loading = store.loadTaskWorkspace("A");
		await store.loadTaskWorkspace("A");
		old.resolve({ data: { task_id: "A", version: "old" } });
		await loading;
		expect(store.workspaceSnapshot).toMatchObject({ version: "new" });
	});
});

describe("工作区与实时进度择新", () => {
	it("两边有序号时优先按 sequence 选择，更新快照也能接替实时消息", async () => {
		store.connectWebSocket("A");
		api.getTaskWorkspace.mockResolvedValueOnce({
			data: {
				task_id: "A",
				progress: { ...progress(1, 10), created_at: "2026-09-05T10:02:00Z" },
			},
		});
		await store.loadTaskWorkspace("A");
		sockets[0].message({
			...progress(2, 70),
			created_at: "2026-09-05T10:01:00Z",
		});
		expect(store.latestProgress?.percent).toBe(70);
		api.getTaskWorkspace.mockResolvedValueOnce({
			data: { task_id: "A", progress: progress(3, 90) },
		});
		await store.loadTaskWorkspace("A");
		expect(store.latestProgress?.percent).toBe(90);
	});

	it("快照没有序号时比较 created_at，更新消息和更新快照都能显示", async () => {
		store.connectWebSocket("A");
		api.getTaskWorkspace.mockResolvedValueOnce({
			data: {
				task_id: "A",
				progress: {
					...progress(1, 10),
					sequence: null,
					created_at: "2026-09-05T10:00:00Z",
				},
			},
		});
		await store.loadTaskWorkspace("A");
		sockets[0].message({
			...progress(2, 70),
			created_at: "2026-09-05T10:01:00Z",
		});
		expect(store.latestProgress?.percent).toBe(70);
		api.getTaskWorkspace.mockResolvedValueOnce({
			data: {
				task_id: "A",
				progress: {
					...progress(3, 90),
					sequence: null,
					created_at: "2026-09-05T10:02:00Z",
				},
			},
		});
		await store.loadTaskWorkspace("A");
		expect(store.latestProgress?.percent).toBe(90);
	});

	it("快照刷新失败后保留产物，同时继续显示较新的实时进度", async () => {
		vi.spyOn(console, "error").mockImplementation(() => {});
		store.connectWebSocket("A");
		api.getTaskWorkspace.mockResolvedValueOnce({
			data: { task_id: "A", progress: progress(1, 10) },
		});
		await store.loadTaskWorkspace("A");
		sockets[0].message(progress(2, 70));
		api.getTaskWorkspace.mockRejectedValueOnce(new Error("offline"));
		await store.loadTaskWorkspace("A");
		expect(store.workspaceSnapshot?.progress.percent).toBe(10);
		expect(store.latestProgress?.percent).toBe(70);
	});

	it.each([undefined, "invalid-time"])(
		"无可比较的时间/序号时使用实际刷新先后：%s",
		async (createdAt) => {
			store.connectWebSocket("A");
			const snapshot = {
				...progress(1, 10),
				sequence: null,
				created_at: createdAt,
			};
			api.getTaskWorkspace.mockResolvedValueOnce({
				data: { task_id: "A", progress: snapshot },
			});
			await store.loadTaskWorkspace("A");
			sockets[0].message({ ...snapshot, percent: 70 });
			expect(store.latestProgress?.percent).toBe(70);
			api.getTaskWorkspace.mockResolvedValueOnce({
				data: { task_id: "A", progress: { ...snapshot, percent: 90 } },
			});
			await store.loadTaskWorkspace("A");
			expect(store.latestProgress?.percent).toBe(90);
		},
	);
});

describe("项目会话隔离", () => {
	it("切换后忽略旧连接回调、历史和审批响应", async () => {
		const oldHistory = deferred<{ data: Message[] }>();
		const oldApproval = deferred<{
			data: { pending: ApprovalMessage; status: string };
		}>();
		api.getTaskMessages.mockReturnValueOnce(oldHistory.promise);
		api.getPendingApproval.mockReturnValueOnce(oldApproval.promise);
		store.connectWebSocket("A");
		const loadHistory = store.loadTaskMessages("A");
		const loadApproval = store.loadPendingApproval("A");
		store.connectWebSocket("B");
		sockets[1].message({
			id: "B-start",
			msg_type: "system",
			type: "info",
			task_status: "running",
		});
		sockets[1].status("connected");
		await flushPromises();
		sockets[0].message(approval("late"));
		sockets[0].status("disconnected");
		oldHistory.resolve({ data: [approval("old")] });
		oldApproval.resolve({
			data: { pending: approval("old"), status: "awaiting_approval" },
		});
		await Promise.all([loadHistory, loadApproval]);
		expect(store.messages.map((message) => message.id)).toEqual(["B-start"]);
		expect(store.pendingApproval).toBeNull();
		expect(store.isRunning).toBe(true);
		expect(store.wsStatus).toBe("connected");
		expect(localStorage.getItem("currentTaskId")).toBe("B");
	});

	it("迟到的续跑响应不能把当前项目从 B 切回 A", async () => {
		const resume = deferred<{ data: { success: boolean; message: string } }>();
		api.resumeTask.mockReturnValue(resume.promise);
		store.connectWebSocket("A");
		const resuming = store.resumeTask("A", "coordinator");
		store.connectWebSocket("B");
		sockets[1].message(approval("B"));
		resume.resolve({ data: { success: true, message: "ok" } });
		await resuming;
		expect(localStorage.getItem("currentTaskId")).toBe("B");
		expect(sockets).toHaveLength(2);
		expect(store.pendingApproval?.checkpoint_id).toBe("B");
		expect(store.isRunning).toBe(false);
	});

	it("批准响应到达前已收到下一节点审批时保留新审批并保持连接", async () => {
		const decision = deferred<{
			data: { success: boolean; message: string };
		}>();
		api.submitApproval.mockReturnValue(decision.promise);
		store.connectWebSocket("A");
		sockets[0].message(approval("first", 1));
		const deciding = store.decideApproval("A", "approve");
		sockets[0].message(approval("second", 3));
		decision.resolve({ data: { success: true, message: "ok" } });
		await deciding;
		expect(store.pendingApproval?.checkpoint_id).toBe("second");
		expect(store.isRunning).toBe(false);
		expect(sockets).toHaveLength(1);
	});
});
