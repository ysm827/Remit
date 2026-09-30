import ProjectFiles from "@/pages/team/ProjectFiles.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ files: vi.fn(), detail: vi.fn() }));
vi.mock("@/apis/filesApi", () => ({ getFiles: api.files, getFileDownloadUrl: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: { get: api.detail } }));
vi.mock("@/apis/submitModelingApi", () => ({ explainModelingSubmissionFailure: (e: Error) => e.message }));
beforeEach(() => {
 vi.clearAllMocks();
 api.files.mockResolvedValue({ data: [{ filename: "result.csv", download_url: "/result.csv" }] });
 api.detail.mockResolvedValue({ data: { problem: { ques_all: "已保存的题面" } } });
});

it("手动刷新有等待反馈、防止重复请求，并明确告知没有新内容", async () => {
 const wrapper = mount(ProjectFiles, { props: { task_id: "one", sequence: 0 } });
 await flushPromises();
 await wrapper.get('nav[aria-label="成果导航"] button:nth-child(3)').trigger("click");
 let finish!: (value: unknown) => void;
 api.detail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
 const button = wrapper.get<HTMLButtonElement>('button[aria-label="刷新项目成果"]');
 await button.trigger("click");
 expect(button.element.disabled).toBe(true);
 expect(wrapper.get('[role="status"]').text()).toContain("正在核对");
 expect(wrapper.text()).toContain("已保存的题面");
 await button.trigger("click");
 expect(api.files).toHaveBeenCalledTimes(2);
 finish({ data: { problem: { ques_all: "已保存的题面" } } });
 await flushPromises();
 expect(button.element.disabled).toBe(false);
 expect(wrapper.get('[role="status"]').text()).toContain("暂无变化");
 wrapper.unmount();
});

it("失败保留已有成果，重试后显示新内容", async () => {
 const wrapper = mount(ProjectFiles, { props: { task_id: "one", sequence: 0 } });
 await flushPromises();
 await wrapper.get('nav[aria-label="成果导航"] button:nth-child(3)').trigger("click");
 api.detail.mockRejectedValueOnce(new Error("连接中断"));
 await wrapper.get("button").trigger("click");
 await flushPromises();
 expect(wrapper.get('[role="alert"]').text()).toContain("连接中断");
 expect(wrapper.text()).toContain("已保存的题面");
 api.detail.mockResolvedValueOnce({ data: { problem: { ques_all: "补充后的题面" } } });
 await wrapper.get("button").trigger("click");
 await flushPromises();
 expect(wrapper.find('[role="alert"]').exists()).toBe(false);
 expect(wrapper.text()).toContain("补充后的题面");
 expect(wrapper.text()).toContain("新内容已同步");
 wrapper.unmount();
});

it("切换项目时丢弃旧请求的结果，并读取新项目", async () => {
 let finish!: (value: unknown) => void;
 api.detail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
 const wrapper = mount(ProjectFiles, { props: { task_id: "one", sequence: 0 } });
 await wrapper.setProps({ task_id: "two" });
 api.detail.mockResolvedValue({ data: { problem: { ques_all: "新项目题面" } } });
 finish({ data: { problem: { ques_all: "旧项目题面" } } });
 await flushPromises();
 expect(api.files).toHaveBeenLastCalledWith("two");
 await wrapper.get('nav[aria-label="成果导航"] button:nth-child(3)').trigger("click");
 expect(wrapper.text()).toContain("新项目题面");
 expect(wrapper.text()).not.toContain("旧项目题面");
 wrapper.unmount();
});


it("默认聚焦小问结果，题面和文件按入口查看，刷新保留当前详情", async () => {
 api.detail.mockResolvedValue({ data: { problem: {ques_all: "很长的赛题原文"}, results: {
  ques1: { coder_response: {code_response: "## 核心结果\n能耗为 59.6 kWh。"}, quality_report: {status:"pass",type_specific:{objectives_detail:{energy_kWh:{model:59.6,baseline:60.5}}}}, modeler_review:{verdict:"manual_review",summary:"需要核对能耗口径"}},
  eda: {execution_summary:{run_summary:"读取了数据"}}
 }}});
 const wrapper=mount(ProjectFiles,{props:{task_id:"one",sequence:0}});
 await flushPromises();
 expect(wrapper.text()).toContain("59.6");
 expect(wrapper.text()).toContain("待核验");
 expect(wrapper.text()).not.toContain("很长的赛题原文");
 expect(wrapper.findAll('a.file')).toHaveLength(0);
 await wrapper.get('.card-link').trigger('click');
 expect(wrapper.text()).toContain("需要核对能耗口径");
 await wrapper.get('[aria-label="结果详情导航"] button:nth-child(3)').trigger('click');
 await wrapper.get('[aria-label="刷新项目成果"]').trigger('click'); await flushPromises();
 expect(wrapper.get('[aria-label="结果详情导航"] [aria-current]').text()).toBe("核验依据");
 expect(wrapper.text()).not.toContain("计算结论原文");
 wrapper.unmount();
});

it("文件分页与分类搜索限制单页长度", async () => {
 api.files.mockResolvedValue({data:Array.from({length:31},(_,i)=>({filename:`plot-${i}.png`,download_url:`/plot-${i}.png`}))});
 const wrapper=mount(ProjectFiles,{props:{task_id:"one",sequence:0}});await flushPromises();
 await wrapper.get('[aria-label="成果导航"] button:nth-child(4)').trigger('click');
 expect(wrapper.findAll('a.file')).toHaveLength(12);
 await wrapper.get('.pagination button:last-child').trigger('click');
 expect(wrapper.findAll('a.file')[0].text()).toContain('plot-12.png');
 await wrapper.get('input').setValue('plot-30');
 expect(wrapper.findAll('a.file')).toHaveLength(1);
 expect(wrapper.text()).toContain('1 / 1');wrapper.unmount();
});
