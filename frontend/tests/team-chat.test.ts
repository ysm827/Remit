import { type TeamEvent, mergeTeamEvents } from "@/apis/teamApi";
import TeamChat from "@/pages/team/TeamChat.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
	getTaskHistory: vi.fn(),
	getCompetitions: vi.fn(),
	getPaperProposals: vi.fn(),
	updateProject: vi.fn(),
	deleteProject: vi.fn(),
	uploadProjectAttachments: vi.fn(),
	route: { query: {} as Record<string, string> },
	getTeamState: vi.fn(),
	sendTeamMessage: vi.fn(),
	submitModelingTask: vi.fn(),
	push: vi.fn(),
}));
vi.mock("@/apis/teamApi", async (original) => ({
	...(await original<typeof import("@/apis/teamApi")>()),
	getTeamState: api.getTeamState,
	getProjects: api.getTaskHistory,
	prepareProject: api.submitModelingTask,
	getCompetitions: api.getCompetitions,
	getPaperProposals: api.getPaperProposals,
	updateProject: api.updateProject,
	deleteProject: api.deleteProject,
	uploadProjectAttachments: api.uploadProjectAttachments,
	sendTeamMessage: api.sendTeamMessage,
}));
vi.mock("@/apis/submitModelingApi", () => ({
	submitModelingTask: api.submitModelingTask,
	explainModelingSubmissionFailure: (cause: Error) => cause.message,
}));
vi.mock("@/pages/chat/components/ApiDialog.vue", () => ({
	default: { template: "<div />" },
}));
vi.mock("@/components/ProblemPdfDropzone.vue", () => ({
	default: { template: "<div />" },
}));
vi.mock("@/pages/team/HumanApprovalCard.vue", () => ({
	default: {
		template:
			"<div><button @click=\"$emit('approve')\">批准当前步骤</button><button @click=\"$emit('explain')\">让 AI 解释</button></div>",
	},
}));
vi.mock("vue-router", () => ({
	useRouter: () => ({ push: api.push }),
	useRoute: () => api.route,
	onBeforeRouteLeave: vi.fn(),
	RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
}));

vi.mock("@/pages/writing/PaperEditor.vue", () => ({
	default: { template: "<div>论文源码与 PDF</div>" },
}));
vi.mock("@/pages/team/ProjectFiles.vue", () => ({
	default: { template: "<div>文件与结果</div>" },
}));
class Stream {
	static latest: Stream;
	onmessage: ((event: { data: string }) => void) | null = null;
	onerror: (() => void) | null = null;
	onopen: (() => void) | null = null;
	close = vi.fn();
	addEventListener = vi.fn();
	constructor() {
		Stream.latest = this;
	}
	update(value: unknown) {
		this.onmessage?.({ data: JSON.stringify(value) });
	}
}
const state = {
	task_id: "project-1",
	title: "预测项目",
	status: "chat",
	steps: [
		{ id: "modeler", role: "modeler", label: "总体建模", status: "running" },
	],
	pending_approval: null,
	directives: [],
	commands: [],
	writing: {},
};
const event: TeamEvent = {
	seq: 1,
	at: "2026-09-27T08:00:00Z",
	role: "coder",
	kind: "tool",
	content: "执行 Python",
	data: {
		tool_name: "execute_code",
		input: { code: "print(42)" },
		output: [{ msg: "42" }],
	},
};

describe("团队对话调度与恢复", () => {
	it("大量重复心跳不挤掉默认可见的关键进展", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		Stream.latest.update({ state, events: [
			{ ...event, seq: 1, kind: 'system', content: '已读取 18 个数据文件，仍有 4 项待核验' },
			...Array.from({ length: 390 }, (_, i) => ({ ...event, seq: i + 2, kind: 'activity', content: '协调手正在输出…' })),
		] });
		await flushPromises();
		expect(wrapper.get('.activity-group').text()).toContain('已读取 18 个数据文件');
		expect(wrapper.findAll('.activity-entry')).toHaveLength(0);
		expect(wrapper.text()).not.toContain('查看更早的记录');
		wrapper.unmount();
	});
	it("计划留在生成位置，后续消息和思考状态排在它之后", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		const plan = { id: "plan-1", understanding: "运输计划", steps: ["计算载荷"], questions: [], attachments: [] };
		Stream.latest.update({ state: { ...state, preflight: plan, commands: [{ status: "running" }] }, events: [
			{ ...event, seq: 1, role: "coordinator", kind: "preflight", data: plan },
			{ ...event, seq: 2, role: "coordinator", kind: "reply", content: "请确认" },
			{ ...event, seq: 3, role: "user", kind: "chat", content: "先求解第一问" },
		] });
		await flushPromises();
		const card = wrapper.get('[aria-label="赛题预读计划"]').element;
		const message = wrapper.findAll('article.event').find(node => node.text().includes('先求解第一问'))!.element;
		expect(card.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(message.compareDocumentPosition(wrapper.get('.thinking').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		const updated = { ...plan, id: "plan-2", understanding: "更新的计划" };
		Stream.latest.update({ state: { ...state, preflight: updated }, events: [
			{ ...event, seq: 4, role: "coordinator", kind: "preflight", data: updated },
			{ ...event, seq: 5, role: "user", kind: "chat", content: "确认新计划" },
		] });
		await flushPromises();
		expect(wrapper.findAll('[aria-label="赛题预读计划"]')).toHaveLength(1);
		const newCard = wrapper.get('[aria-label="赛题预读计划"]').element;
		expect(message.compareDocumentPosition(newCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		const latest = wrapper.findAll('article.event').find(node => node.text().includes('确认新计划'))!.element;
		expect(newCard.compareDocumentPosition(latest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		wrapper.unmount();
	});
	it("关键消息直接展示，四个角色可区分，思考与工具输出收进详情", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		Stream.latest.update({ state, events: [
			...['coordinator', 'modeler', 'coder', 'writer'].map((role, i) => ({ ...event, seq: i + 1, role, kind: 'reply', content: `关键结论${i + 1}` })),
			{ ...event, seq: 5, kind: 'agent', content: '内部思考过程' },
			{ ...event, seq: 6, kind: 'tool', content: 'execute_code', data: { input: { code: 'raw-debug-code' } } },
			{ ...event, seq: 7, kind: 'error', content: '本步骤失败，请检查附件' },
		] });
		await flushPromises();
		const headings = wrapper.findAll('.role-heading');
		expect(headings.slice(0, 4).map(node => node.text())).toEqual(['协调手', '建模手', '代码手', '论文手']);
		expect(new Set(headings.slice(0, 4).map(node => node.get('svg').html())).size).toBe(4);
		expect(wrapper.findAll('article.event')).toHaveLength(5);
		expect(wrapper.get('.event-error').text()).toContain('本步骤失败，请检查附件');
		expect(wrapper.text()).not.toContain('内部思考过程');
		expect(wrapper.text()).not.toContain('raw-debug-code');
		expect(wrapper.findAll('.activity-entry')).toHaveLength(0);
		wrapper.unmount();
	});
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
		localStorage.clear();
		vi.stubGlobal("EventSource", Stream);
		api.route.query = {};
		api.getCompetitions.mockResolvedValue({
			data: [
				{ id: "cumcm", name: "国赛", year: 2026 },
				{ id: "gmcm", name: "华为杯", year: 2026 },
			],
		});
		api.getPaperProposals.mockResolvedValue({ data: [] });
		api.getTaskHistory.mockResolvedValue({ data: [] });
		api.getTeamState.mockResolvedValue({ data: state });
		api.sendTeamMessage.mockResolvedValue({ data: { status: "running" } });
		api.deleteProject.mockResolvedValue({ data: { deleted: true } });
		api.uploadProjectAttachments.mockResolvedValue({
			data: { files: ["data.csv"] },
		});
	});
	afterEach(() => vi.unstubAllGlobals());
	it("解释成果仅发送通俗解释请求，不附带批准动作", async () => {
		api.getTeamState.mockResolvedValue({
			data: {
				...state,
				status: "awaiting_approval",
				pending_approval: { checkpoint_id: "review-1", node_id: "modeler" },
			},
		});
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		const button = wrapper
			.findAll("button")
			.find((item) => item.text() === "让 AI 解释");
		await button?.trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage).toHaveBeenCalledTimes(1);
		const body = api.sendTeamMessage.mock.calls[0][1];
		expect(body.action).toBeUndefined();
		expect(body.content).toContain("具体例子");
		expect(body.content).toContain("只解释，不批准");
		wrapper.unmount();
	});
	it("失败后由用户点击重试当前步骤，打开页面不自动重跑", async () => {
		api.getTeamState.mockResolvedValue({
			data: { ...state, status: "failed" },
		});
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		expect(api.sendTeamMessage).not.toHaveBeenCalled();
		await wrapper.get(".recovery-notice button").trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[0][0]).toBe("project-1");
		expect(api.sendTeamMessage.mock.calls[0][1]).toMatchObject({
			action: "resume",
			content: "重试当前失败步骤",
		});
		wrapper.unmount();
	});
	it("普通对话没有计划时仍能导入附件和文件夹", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		await wrapper.get('[aria-label="添加赛题或数据"]').trigger("click");
		expect(wrapper.get(".attachment-menu").text()).toContain("数据文件夹");
		const file = new File(["x\n1"], "data.csv");
		Object.defineProperty(file, "webkitRelativePath", {
			value: "数据/train/data.csv",
		});
		const input = wrapper.get("input[webkitdirectory]");
		Object.defineProperty(input.element, "files", { value: [file] });
		await input.trigger("change");
		await flushPromises();
		expect(api.uploadProjectAttachments.mock.calls[0][0]).toBe("project-1");
		expect(
			api.uploadProjectAttachments.mock.calls[0][1][0].webkitRelativePath,
		).toBe("数据/train/data.csv");
		expect(wrapper.text()).toContain("已导入 1 个文件");
		wrapper.unmount();
	});
	it("首页按文件夹汇总附件，可单独发送并保留子目录路径", async () => {
		api.submitModelingTask.mockResolvedValue({
			data: { task_id: "folder-project" },
		});
		const wrapper = mount(TeamChat);
		await flushPromises();
		const files = ["data/a.csv", "data/sub/a.csv", "data/.DS_Store"].map(
			(path) => {
				const file = new File(["x\n1"], path.split("/").at(-1) || "a.csv");
				Object.defineProperty(file, "webkitRelativePath", { value: path });
				return file;
			},
		);
		const input = wrapper.get("input[webkitdirectory]");
		Object.defineProperty(input.element, "files", { value: files });
		await input.trigger("change");
		await flushPromises();
		expect(wrapper.get(".attachment-list").text()).toContain("2 个文件");
		expect(wrapper.text()).toContain("已跳过 1 个");
		await wrapper.get('[aria-label="发送"]').trigger("click");
		await flushPromises();
		expect(
			api.submitModelingTask.mock.calls[0][1].map(
				(file: File) => file.webkitRelativePath,
			),
		).toEqual(["data/a.csv", "data/sub/a.csv"]);
		expect(api.push).toHaveBeenCalledWith("/project/folder-project");
		wrapper.unmount();
	});
	it("问候只显示回复，隐藏新旧内部同步标记并保留真实执行记录", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		Stream.latest.update({
			state,
			events: [
				{
					...event,
					seq: 1,
					role: "coordinator",
					kind: "reply",
					content: "模型返回的问候",
				},
				{
					...event,
					seq: 2,
					kind: "system",
					event_key: "archive-imported",
					content: "历史执行记录已同步到团队对话",
				},
				{ ...event, seq: 3, kind: "internal", content: "内部同步标记" },
			],
		});
		await flushPromises();
		expect(wrapper.text()).toContain("模型返回的问候");
		expect(wrapper.find(".activity-group").exists()).toBe(false);
		Stream.latest.update({ state, events: [{ ...event, seq: 4 }] });
		await flushPromises();
		expect(wrapper.findAll(".activity-entry")).toHaveLength(0);
		expect(wrapper.text()).toContain("工具调用 1 次");
		expect(wrapper.text()).not.toContain("历史执行记录已同步");
		wrapper.unmount();
	});
	it("归档项目删除先确认，取消不请求，成功后移出列表并离开已删项目", async () => {
		api.getTaskHistory.mockResolvedValue({
			data: [{ task_id: "project-1", title: "待删除项目", archived: true }],
		});
		const wrapper = mount(TeamChat, {
			props: { task_id: "project-1" },
			attachTo: document.body,
		});
		await flushPromises();
		await wrapper.get(".rail-caption button").trigger("click");
		await wrapper
			.get('button[aria-label="管理项目 待删除项目"]')
			.trigger("click");
		await wrapper.get(".project-menu .danger-text").trigger("click");
		await flushPromises();
		expect(api.deleteProject).not.toHaveBeenCalled();
		expect(wrapper.get('[role="alertdialog"]').text()).toContain("无法恢复");
		await wrapper.get('[role="alertdialog"] footer button').trigger("click");
		await flushPromises();
		expect(api.deleteProject).not.toHaveBeenCalled();
		await wrapper
			.get('button[aria-label="管理项目 待删除项目"]')
			.trigger("click");
		await wrapper.get(".project-menu .danger-text").trigger("click");
		await flushPromises();
		await wrapper.get(".delete-confirm").trigger("click");
		await flushPromises();
		expect(api.deleteProject).toHaveBeenCalledExactlyOnceWith("project-1");
		expect(
			wrapper.find('button[aria-label="管理项目 待删除项目"]').exists(),
		).toBe(false);
		expect(Stream.latest.close).toHaveBeenCalled();
		expect(api.push).toHaveBeenCalledWith("/home");
		wrapper.unmount();
	});
	it("删除失败保留项目和确认框并展示错误", async () => {
		api.getTaskHistory.mockResolvedValue({
			data: [{ task_id: "project-1", title: "保留项目", archived: true }],
		});
		api.deleteProject.mockRejectedValueOnce(new Error("文件正在使用"));
		const wrapper = mount(TeamChat, { attachTo: document.body });
		await flushPromises();
		await wrapper.get(".rail-caption button").trigger("click");
		await wrapper
			.get('button[aria-label="管理项目 保留项目"]')
			.trigger("click");
		await wrapper.get(".project-menu .danger-text").trigger("click");
		await flushPromises();
		await wrapper.get(".delete-confirm").trigger("click");
		await flushPromises();
		expect(wrapper.get('[role="alert"]').text()).toBe("文件正在使用");
		expect(
			wrapper.find('button[aria-label="管理项目 保留项目"]').exists(),
		).toBe(true);
		expect(api.push).not.toHaveBeenCalled();
		wrapper.unmount();
	});
	it("运行中问进度直接发送为对话，不带重启或调整时机", async () => {
		api.getTeamState.mockResolvedValue({ data: { ...state, status: "running" } });
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		await wrapper.get("textarea").setValue("现在到底进行得怎么样了");
		await wrapper.get('button[aria-label="发送"]').trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage).toHaveBeenCalledTimes(1);
		expect(api.sendTeamMessage.mock.calls[0][1]).toMatchObject({ content: "现在到底进行得怎么样了", conversation_only: true });
		expect(api.sendTeamMessage.mock.calls[0][1].timing).toBeUndefined();
		expect(api.sendTeamMessage.mock.calls[0][1].action).toBeUndefined();
		expect(wrapper.find('[aria-label="选择调整时机"]').exists()).toBe(false);
		wrapper.unmount();
	});
	it("仅主动调整任务时选择时机，普通发送保持对话", async () => {
		api.getTeamState.mockResolvedValue({
			data: { ...state, status: "running" },
		});
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		await wrapper.get("textarea").setValue("换个方法试试");
		await wrapper.findAll("button").find(button => button.text() === "调整任务")?.trigger("click");
		expect(api.sendTeamMessage).not.toHaveBeenCalled();
		expect(wrapper.find('[aria-label="选择调整时机"]').exists()).toBe(true);
		await wrapper.findAll(".adjustment-menu > button")[1]?.trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[0][1]).toMatchObject({
			content: "换个方法试试",
			timing: "after_step",
		});
		wrapper.unmount();
	});
	it("助手正文支持排版，用户消息保留原文", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		Stream.latest.update({
			state,
			events: [
				{
					...event,
					kind: "reply",
					role: "coordinator",
					content: "**模型建议**\n\n- 先检查数据\n- 再比较基线",
				},
			],
		});
		await flushPromises();
		expect(wrapper.get(".markdown-body strong").text()).toBe("模型建议");
		expect(wrapper.findAll(".markdown-body li")).toHaveLength(2);
		wrapper.unmount();
	});
	it("桌面侧栏可折叠恢复并记住选择，普通对话不挂载论文编辑器", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		expect(wrapper.text()).not.toContain("论文源码与 PDF");
		const toggle = wrapper.get('button[aria-label="切换项目导航"]');
		await toggle.trigger("click");
		expect(wrapper.classes()).toContain("sidebar-collapsed");
		expect(toggle.attributes("aria-expanded")).toBe("false");
		wrapper.unmount();
		const reopened = mount(TeamChat);
		expect(reopened.classes()).toContain("sidebar-collapsed");
		await reopened.get('button[aria-label="切换项目导航"]').trigger("click");
		expect(reopened.classes()).not.toContain("sidebar-collapsed");
		expect(localStorage.getItem("remit-sidebar-collapsed")).toBe("false");
		reopened.unmount();
	});
	it("重连按序号去重，保留工具输入输出和后续角色记录", async () => {
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		Stream.latest.update({ state, events: [event] });
		Stream.latest.update({
			state,
			events: [
				event,
				{
					...event,
					seq: 2,
					role: "writer",
					kind: "writing",
					content: "正在写摘要",
				},
			],
		});
		await flushPromises();
		expect(wrapper.findAll(".activity-group")).toHaveLength(1);
		expect(wrapper.get(".activity-group").attributes("open")).toBeUndefined();
		await wrapper.get('button[aria-label="对话显示选项"]').trigger("click");
		await wrapper.get(".timeline-filters input").setValue(true);
		expect(wrapper.get(".raw-log").attributes("open")).toBeDefined();
		expect(wrapper.text()).toContain("print(42)");
		const raw = wrapper.get(".raw-log");
		(raw.element as HTMLDetailsElement).open = true;
		await raw.trigger("toggle");
		expect(wrapper.text()).toContain("print(42)");
		expect(wrapper.text()).toContain("正在写摘要");
		wrapper.unmount();
		expect(Stream.latest.close).toHaveBeenCalledOnce();
	});
	it("请求失败保留草稿和幂等编号，重试不重复派活", async () => {
		api.sendTeamMessage.mockRejectedValueOnce(new Error("网络中断"));
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		await wrapper.get("textarea").setValue("请代码手保存误差图");
		await wrapper.get("button[aria-label='发送']").trigger("click");
		await flushPromises();
		const first = api.sendTeamMessage.mock.calls[0][1];
		expect(wrapper.get("textarea").element.value).toContain("保存误差图");
		expect(wrapper.text()).toContain("网络中断");
		await wrapper.get("button[aria-label='发送']").trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[1][1].request_id).toBe(
			first.request_id,
		);
		expect(wrapper.get("textarea").element.value).toBe("");
		wrapper.unmount();
	});
	it("批准附带当前检查点，停止使用独立控制动作", async () => {
		api.getTeamState.mockResolvedValue({
			data: {
				...state,
				status: "running",
				pending_approval: { checkpoint_id: "checkpoint-new" },
			},
		});
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		await wrapper
			.findAll("button")
			.find((button) => button.text() === "批准当前步骤")
			?.trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[0][1]).toMatchObject({
			action: "approve",
			checkpoint_id: "checkpoint-new",
		});
		await wrapper.get("button[aria-label='停止建模']").trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[1][1].action).toBe("stop");
		wrapper.unmount();
	});
	it("首页问题进入同一个项目对话", async () => {
		api.submitModelingTask.mockResolvedValue({
			data: { task_id: "new-project" },
		});
		const wrapper = mount(TeamChat);
		await wrapper
			.get("textarea")
			.setValue("根据温度数据预测用电量，输出误差分析");
		await wrapper.get("button[aria-label='发送']").trigger("click");
		await flushPromises();
		expect(api.submitModelingTask.mock.calls[0][0].competition_id).toBe(
			"cumcm",
		);
		expect(wrapper.find("img[alt='Remit Logo']").exists()).toBe(true);
		expect(wrapper.text()).not.toContain("workspace");
		expect(api.submitModelingTask.mock.calls[0][0].ques_all).toContain(
			"温度数据",
		);
		expect(api.push).toHaveBeenCalledWith("/project/new-project");
		wrapper.unmount();
	});
	it("计划确认携带当前计划版本，预读不直接执行", async () => {
		api.getTeamState.mockResolvedValue({
			data: {
				...state,
				status: "ready",
				preflight: {
					id: "plan-current",
					understanding: "数据已就绪",
					steps: ["基线比较"],
					questions: [],
					attachments: [],
				},
			},
		});
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		expect(api.sendTeamMessage).not.toHaveBeenCalled();
		await wrapper.get(".review-card .primary-button").trigger("click");
		await flushPromises();
		expect(api.sendTeamMessage.mock.calls[0][1]).toMatchObject({
			action: "start",
			plan_id: "plan-current",
		});
		wrapper.unmount();
	});
	it("论文页沿用项目导航，并可打开同一段对话", async () => {
		api.route.query = { view: "paper" };
		const wrapper = mount(TeamChat, { props: { task_id: "project-1" } });
		await flushPromises();
		expect(wrapper.text()).toContain("论文源码与 PDF");
		expect(wrapper.find('a[href="/projects"]').exists()).toBe(false);
		await wrapper.get('button[aria-label="切换项目对话"]').trigger("click");
		expect(wrapper.get(".copilot").isVisible()).toBe(true);
		wrapper.unmount();
	});
	it("乱序重放不会丢失已有事件", () => {
		expect(
			mergeTeamEvents(
				[{ ...event, seq: 3 }],
				[{ ...event, seq: 2 }, event, { ...event, seq: 3 }],
			).map((item) => item.seq),
		).toEqual([1, 2, 3]);
	});
});
