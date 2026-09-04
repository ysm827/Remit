import App from "@/App.vue";
import TaskPage from "@/pages/task/index.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

const task = vi.hoisted(() => ({
	isRunning: true,
	pendingApproval: null,
	loadTaskMessages: vi.fn(),
	loadTaskHistory: vi.fn(),
	connectWebSocket: vi.fn(),
	closeWebSocket: vi.fn(),
	stopTask: vi.fn(),
}));
const api = vi.hoisted(() => ({
	getWriterSeque: vi.fn(),
	getResumeOptions: vi.fn(),
}));
vi.mock("@/stores/task", () => ({ useTaskStore: () => task }));
vi.mock("@/apis/commonApi", () => api);
vi.mock("@/components/ui/toast/Toaster.vue", () => ({
	default: { template: "<div />" },
}));
vi.mock("@/components/ui/toast", () => ({
	useToast: () => ({ toast: vi.fn() }),
}));
vi.mock("@/pages/task/components/ProjectWorkspaceShell.vue", () => ({
	default: {
		props: ["taskId"],
		emits: ["stop"],
		template:
			'<section><span data-test="task">{{ taskId }}</span><button @click="$emit(\'stop\')">stop</button></section>',
	},
}));

let wrapper: ReturnType<typeof mount> | undefined;
beforeEach(() => {
	vi.resetAllMocks();
	task.isRunning = true;
	task.loadTaskMessages.mockResolvedValue(undefined);
	task.loadTaskHistory.mockResolvedValue(undefined);
	task.stopTask.mockResolvedValue({ success: false });
	api.getWriterSeque.mockResolvedValue({ data: [] });
});
afterEach(() => wrapper?.unmount());

async function openProject() {
	const router = createRouter({
		history: createMemoryHistory(),
		routes: [
			{
				path: "/project/:projectId/:stage?",
				component: TaskPage,
				props: (route) => ({ task_id: route.params.projectId }),
			},
		],
	});
	await router.push("/project/A/overview");
	wrapper = mount(App, {
		global: { plugins: [router], stubs: { Dialog: true } },
	});
	await flushPromises();
	return router;
}

describe("实际任务页路由生命周期", () => {
	it("A → B 重载消息和连接，停止按钮只操作 B", async () => {
		const router = await openProject();
		await router.push("/project/B/overview");
		await flushPromises();
		expect(task.loadTaskMessages.mock.calls).toEqual([["A"], ["B"]]);
		expect(task.connectWebSocket.mock.calls).toEqual([["A"], ["B"]]);
		expect(task.closeWebSocket).toHaveBeenCalledWith("A");
		expect(wrapper?.get('[data-test="task"]').text()).toBe("B");
		await wrapper?.get("button").trigger("click");
		expect(task.stopTask).toHaveBeenCalledWith("B");
	});

	it("同项目切换阶段保留连接，不重复初始化任务", async () => {
		const router = await openProject();
		await router.push("/project/A/paper");
		await flushPromises();
		expect(task.connectWebSocket).toHaveBeenCalledTimes(1);
		expect(task.closeWebSocket).not.toHaveBeenCalled();
	});

	it("先连接后加载历史，且离开 A 后迟到的初始化不会重新连接或创建计时器", async () => {
		let finishOld!: () => void;
		const old = new Promise<void>((resolve) => {
			finishOld = resolve;
		});
		task.loadTaskMessages.mockReturnValueOnce(old).mockResolvedValue(undefined);
		const interval = vi.spyOn(globalThis, "setInterval");
		const router = await openProject();
		expect(task.connectWebSocket).toHaveBeenCalledWith("A");
		expect(task.connectWebSocket.mock.invocationCallOrder[0]).toBeLessThan(
			task.loadTaskMessages.mock.invocationCallOrder[0],
		);
		await router.push("/project/B/overview");
		await flushPromises();
		const timerCount = interval.mock.calls.length;
		finishOld();
		await flushPromises();
		expect(task.connectWebSocket.mock.calls).toEqual([["A"], ["B"]]);
		expect(api.getWriterSeque).toHaveBeenCalledTimes(1);
		expect(interval).toHaveBeenCalledTimes(timerCount);
	});
});
