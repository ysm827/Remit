import RuntimePanel from "@/pages/team/RuntimePanel.vue";
import ChapterPlan from "@/pages/writing/ChapterPlan.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: api }));
beforeEach(() => vi.clearAllMocks());

it("环境检查仅由用户启动，并阻止重复请求", async () => {
 const wrapper = mount(RuntimePanel);
 expect(api.post).not.toHaveBeenCalled();
 await wrapper.get("button").trigger("click");
 let finish: (value: unknown) => void = () => {};
 api.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
 const run = wrapper.findAll("button").find(node => node.text() === "运行本地自检案例");
 if (!run) throw new Error("缺少自检按钮");
 await run.trigger("click");
 await run.trigger("click");
 expect(api.post).toHaveBeenCalledTimes(1);
 finish({ data: { ready: true, checks: [], elapsed_seconds: 1, scope: "固定代码", runtime: { version: "fixture", executor: "python", launch_mode: "source", data_directory: "fixture" } } });
 await flushPromises();
 expect(wrapper.text()).toContain("本地计算检查通过");
 wrapper.unmount();
});

it("章节计划冲突与折叠不会丢失未保存意见", async () => {
 api.get.mockResolvedValue({ data: { version: "v1", evidence_revision: "e1", notes: "原意见", sections: [] } });
 api.put.mockRejectedValue(new Error("409"));
 const wrapper = mount(ChapterPlan, { props: { taskId: "fixture" } });
 await wrapper.get("button").trigger("click");
 await flushPromises();
 await wrapper.get("textarea").setValue("我的未保存意见");
 await wrapper.findAll("button")[1].trigger("click");
 await flushPromises();
 expect(wrapper.get('[role="alert"]').text()).toContain("本地修改仍保留");
 await wrapper.get("button").trigger("click");
 await wrapper.get("button").trigger("click");
 expect(wrapper.get<HTMLTextAreaElement>("textarea").element.value).toBe("我的未保存意见");
 expect(api.get).toHaveBeenCalledTimes(1);
 wrapper.unmount();
});

it("旧项目的章节计划响应不会覆盖新项目", async () => {
 let finish: (value: unknown) => void = () => {};
 api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
 const wrapper = mount(ChapterPlan, { props: { taskId: "old" } });
 await wrapper.get("button").trigger("click");
 await wrapper.setProps({ taskId: "new" });
 finish({ data: { version: "old", evidence_revision: "old", notes: "旧项目", sections: [] } });
 await flushPromises();
 expect(wrapper.text()).not.toContain("旧项目");
 expect(wrapper.find("textarea").exists()).toBe(false);
 wrapper.unmount();
});
