import ExecutionBudgetRecovery from "@/pages/team/ExecutionBudgetRecovery.vue";
import TaskFailureNotice from "@/pages/team/TaskFailureNotice.vue";
import type { TeamState } from "@/apis/teamApi";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: api }));
const snapshot = { stage_key: "a".repeat(64), used: 48, limit: 48, remaining: 0, node_id: "solve:ques1", label: "第一问" };
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: snapshot }); api.post.mockResolvedValue({ data: { success: true } }); });
const create = () => mount(ExecutionBudgetRecovery, { props: { taskId: "fixture", nodeId: "solve:ques1", sending: false } });

function button(wrapper: VueWrapper, label: string) {
 const found = wrapper.findAll("button").find(x => x.text() === label);
 if (!found) throw new Error(`Button missing: ${label}`);
 return found;
}

it("查看和取消不增加次数，确认展示后的追加量才恢复", async () => {
	const wrapper = create();
	expect(api.get).not.toHaveBeenCalled();
	await wrapper.get("button").trigger("click"); await flushPromises();
	expect(wrapper.text()).toContain("上限调整为 60 次");
	expect(api.post).not.toHaveBeenCalled();
	await button(wrapper, "取消").trigger("click");
	expect(api.post).not.toHaveBeenCalled();
	await wrapper.get("button").trigger("click"); await flushPromises();
	await wrapper.get("input").setValue("3");
	await button(wrapper, "确认追加并继续").trigger("click"); await flushPromises();
	expect(api.post).toHaveBeenCalledWith("/modeling/fixture/resume", {
		node_id: "solve:ques1", execution_budget_extension: { confirmed: true, request_id: expect.stringMatching(/^[0-9a-f]{32}$/), stage_key: snapshot.stage_key, expected_used: 48, expected_limit: 48, additional: 3 },
	});
	expect(wrapper.emitted("resumed")).toHaveLength(1); wrapper.unmount();
});

it("请求未完成时重复点击不会重发，失败重试复用确认编号", async () => {
	const wrapper = create();
	await wrapper.get("button").trigger("click"); await flushPromises();
	let reject: (value: unknown) => void = () => {};
	api.post.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
	const confirm = button(wrapper, "确认追加并继续");
	await confirm.trigger("click"); await confirm.trigger("click");
	expect(api.post).toHaveBeenCalledTimes(1);
	const id = api.post.mock.calls[0][1].execution_budget_extension.request_id;
	reject(new Error("响应丢失")); await flushPromises();
	await confirm.trigger("click"); await flushPromises();
	expect(api.post.mock.calls[1][1].execution_budget_extension.request_id).toBe(id);
	wrapper.unmount();
});

it("不接受小数或越界次数，切换项目后不采用旧响应", async () => {
	const wrapper = create();
	await wrapper.get("button").trigger("click"); await flushPromises();
	await wrapper.get("input").setValue("1.5");
	expect(wrapper.text()).toContain("请输入 1 至 48");
	expect(button(wrapper, "确认追加并继续").attributes("disabled")).toBeDefined();
	let finish: (value: unknown) => void = () => {};
	api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
	await wrapper.get("button").trigger("click");
	await wrapper.setProps({ taskId: "different" });
	finish({ data: snapshot }); await flushPromises();
	expect(wrapper.find("input").exists()).toBe(false);
	expect(api.post).not.toHaveBeenCalled(); wrapper.unmount();
});

it("已有剩余次数时直接恢复，不再次追加", async () => {
	api.get.mockResolvedValue({ data: { ...snapshot, limit: 60, remaining: 12 } });
	const wrapper = create(); await wrapper.get("button").trigger("click"); await flushPromises();
	expect(wrapper.find("input").exists()).toBe(false);
	await button(wrapper, "继续当前阶段").trigger("click"); await flushPromises();
	expect(api.post).toHaveBeenCalledWith("/modeling/fixture/resume", { node_id: "solve:ques1" }); wrapper.unmount();
});

it("额度耗尽面板保留成果入口，移除无效的通用恢复和模型设置按钮", () => {
	const state = { task_id: "fixture", status: "failed", current_node: "solve:ques1", steps: [], writing: { status: "draft" }, failure: { code: "EXECUTION_BUDGET", reason: "额度已用完", saved_result_count: 1 } } as unknown as TeamState;
	const wrapper = mount(TaskFailureNotice, { props: { state, sending: false } });
	expect(wrapper.text()).toContain("查看执行次数并继续");
	expect(wrapper.text()).toContain("查看已保存成果");
	expect(wrapper.text()).not.toContain("从检查点继续");
	expect(wrapper.text()).not.toContain("修改模型配置"); wrapper.unmount();
});
