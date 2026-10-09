import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import ModelBudgetRecovery from "@/pages/team/ModelBudgetRecovery.vue";
import TaskFailureNotice from "@/pages/team/TaskFailureNotice.vue";
import type { TeamState } from "@/apis/teamApi";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: api }));
const snapshot = { stage_key: "a".repeat(64), used: 24, limit: 24, remaining: 0, elapsed_seconds: 900, seconds_limit: 900, remaining_seconds: 0, can_resume: false, phase: "review", node_id: "solve:eda", label: "数据检查" };
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: snapshot }); api.post.mockResolvedValue({ data: { success: true } }); });
const create = () => mount(ModelBudgetRecovery, { props: { taskId: "fixture", nodeId: "solve:eda", sending: false }, global: { stubs: { FloatingPanel: { props: ["open"], template: '<div v-if="open"><slot /></div>' } } } });
function button(wrapper: VueWrapper, label: string) {
    const found = wrapper.findAll("button").find(x => x.text() === label);
    if (!found) throw new Error(`Missing button: ${label}`);
    return found;
}

it("先展示实际消耗和待审查位置，确认后才追加有界额度", async () => {
    const wrapper = create();
    await wrapper.get("button").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("待审查结果");
    expect(wrapper.text()).toContain("追加 6 次调用和 600 秒");
    expect(api.post).not.toHaveBeenCalled();
    await button(wrapper, "确认追加并继续").trigger("click"); await flushPromises();
    expect(api.post).toHaveBeenCalledWith("/modeling/fixture/resume", { node_id: "solve:eda", model_budget_extension: { confirmed: true, request_id: expect.stringMatching(/^[0-9a-f]{32}$/), stage_key: snapshot.stage_key, expected_used: 24, expected_limit: 24, expected_seconds: 900, additional_calls: 6, additional_seconds: 600 } });
    expect(wrapper.emitted("resumed")).toHaveLength(1); wrapper.unmount();
});

it("额度充足只恢复，不再追加", async () => {
    api.get.mockResolvedValue({ data: { ...snapshot, can_resume: true, limit: 30, seconds_limit: 1500 } });
    const wrapper = create(); await wrapper.get("button").trigger("click"); await flushPromises();
    await button(wrapper, "继续当前阶段").trigger("click"); await flushPromises();
    expect(api.post).toHaveBeenCalledWith("/modeling/fixture/resume", { node_id: "solve:eda" }); wrapper.unmount();
});

it("调用次数仍有剩余但时间不足，也必须展示追加确认", async () => {
    api.get.mockResolvedValue({ data: { ...snapshot, used: 20, remaining: 4, remaining_seconds: 44 } });
    const wrapper = create(); await wrapper.get("button").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("确认追加并继续"); expect(api.post).not.toHaveBeenCalled(); wrapper.unmount();
});

it("丢失响应后使用同一确认编号，双击不重复提交", async () => {
    const wrapper = create(); await wrapper.get("button").trigger("click"); await flushPromises();
    let reject: (error: unknown) => void = () => {};
    api.post.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
    const confirm = button(wrapper, "确认追加并继续");
    await confirm.trigger("click"); await confirm.trigger("click");
    expect(api.post).toHaveBeenCalledTimes(1);
    const id = api.post.mock.calls[0][1].model_budget_extension.request_id;
    reject(new Error("response lost")); await flushPromises();
    await confirm.trigger("click"); await flushPromises();
    expect(api.post.mock.calls[1][1].model_budget_extension.request_id).toBe(id); wrapper.unmount();
});

it("切换项目后丢弃旧额度响应", async () => {
    let finish: (value: unknown) => void = () => {};
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const wrapper = create(); await wrapper.get("button").trigger("click");
    await wrapper.setProps({ taskId: "other" }); finish({ data: snapshot }); await flushPromises();
    expect(wrapper.text()).not.toContain("确认追加"); expect(api.post).not.toHaveBeenCalled(); wrapper.unmount();
});

it.each(["failed", "stopped"])("%s 状态都显示额度恢复，不提供无效普通重试", status => {
    const state = { task_id: "fixture", status, current_node: "solve:eda", failure: { code: "MODEL_STAGE_BUDGET", reason: "预算不足" } } as unknown as TeamState;
    const wrapper = mount(TaskFailureNotice, { props: { state, sending: false } });
    expect(wrapper.text()).toContain("额度暂停"); expect(wrapper.text()).toContain("查看模型额度并继续");
    expect(wrapper.text()).not.toContain("重试当前步骤"); expect(wrapper.text()).not.toContain("修改模型配置"); wrapper.unmount();
});
