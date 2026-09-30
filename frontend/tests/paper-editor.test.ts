import PaperEditor from "@/pages/writing/PaperEditor.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
	getPaperWorkspace: vi.fn(),
	getPaperSource: vi.fn(),
	savePaperSource: vi.fn(),
	compilePaper: vi.fn(),
	generatePaper: vi.fn(),
	syncPaper: vi.fn(),
	cancelPaper: vi.fn(),
	setPaperMain: vi.fn(),
	getPaperHistory: vi.fn(),
	writingUrl: (id: string, path = "") => `/writing/${id}${path}`,
}));
vi.mock("@/apis/writingApi", () => api);
vi.mock("vue-router", () => ({
	onBeforeRouteLeave: vi.fn(),
	RouterLink: { template: "<a><slot /></a>" },
}));

describe("论文编辑器保存与编译", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
		api.getPaperWorkspace.mockResolvedValue({
			data: {
				main: "main.tex",
				ready: true,
				revision: "first",
				pdf_available: true,
				files: [{ name: "main.tex", editable: true }],
				inputs: {},
				generation: { status: "idle" },
				compile: { pdf_revision: "first", page_count: 1 },
			},
		});
		api.getPaperSource.mockResolvedValue({
			data: { content: "initial", version: "first" },
		});
		api.savePaperSource.mockResolvedValue({
			data: { version: "saved", revision: "saved" },
		});
		api.compilePaper.mockResolvedValue({ data: { status: "completed" } });
	});
	afterEach(() => vi.useRealTimers());
	it("打开尚无 PDF 的论文页不会自动编译空模板", async () => {
		api.getPaperWorkspace.mockResolvedValue({
			data: {
				main: "main.tex",
				ready: false,
				revision: "first",
				pdf_available: false,
				files: [{ name: "main.tex", editable: true }],
				inputs: {},
				generation: { status: "idle" },
				compile: {},
			},
		});
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		expect(api.compilePaper).not.toHaveBeenCalled();
		await wrapper.get(".compile-button").trigger("click");
		await flushPromises();
		expect(api.compilePaper).toHaveBeenCalledOnce();
		wrapper.unmount();
	});

	it("生成的主文件在轮询后打开，无需用户重新进入", async () => {
        const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
        await flushPromises();
        api.getPaperWorkspace.mockResolvedValue({data: {
            main: "draft-new.tex", ready: true, revision: "new", pdf_available: false,
            files: [{name: "draft-new.tex", editable: true}], inputs: {},
            generation: {status: "completed", file: "draft-new.tex"}, compile: {},
        }});
        api.getPaperSource.mockResolvedValue({data: {content: "generated paper", version: "new"}});
        await vi.advanceTimersByTimeAsync(4000);
        await flushPromises();
        expect(api.getPaperSource).toHaveBeenLastCalledWith("test", "draft-new.tex");
        expect(wrapper.get("textarea").element.value).toBe("generated paper");
        wrapper.unmount();
    });

	it("保存冲突保留正在编辑的内容，并阻止编译", async () => {
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		api.savePaperSource.mockRejectedValue(new Error("文件已被其他窗口修改"));
		await wrapper.get("textarea").setValue("my unsaved changes");
		await vi.advanceTimersByTimeAsync(750);
		await flushPromises();
		expect(wrapper.get("textarea").element.value).toBe("my unsaved changes");
		expect(wrapper.text()).toContain("文件已被其他窗口修改");
		expect(api.compilePaper).not.toHaveBeenCalled();
		wrapper.unmount();
	});

	it("同名草稿增量更新会刷新正文，并显示实际排版问题", async () => {
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		api.getPaperWorkspace.mockResolvedValue({ data: {
			main: "main.tex", ready: true, revision: "chapter-2", pdf_available: true,
			files: [{ name: "main.tex", editable: true }], inputs: {},
			generation: { status: "running", file: "main.tex", section: "symbol", partial: true, completed_sections: ["firstPage", "RepeatQues"] },
			compile: { pdf_revision: "chapter-2", page_count: 2, layout_review: { status: "needs_revision", issues: ["摘要和关键词跨页"] } },
		} });
		api.getPaperSource.mockResolvedValue({ data: { content: "new chapter", version: "chapter-2" } });
		await vi.advanceTimersByTimeAsync(4000);
		await flushPromises();
		expect(wrapper.get("textarea").element.value).toBe("new chapter");
		expect(wrapper.text()).toContain("墨墨正在撰写符号说明");
		expect(wrapper.text()).toContain("已写 2 个章节");
		expect(wrapper.text()).toContain("摘要和关键词跨页");
		wrapper.unmount();
	});

	it("草稿轮询不会覆盖尚未保存的用户修改", async () => {
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		api.savePaperSource.mockRejectedValue(new Error("保存冲突"));
		await wrapper.get("textarea").setValue("my draft");
		api.getPaperWorkspace.mockResolvedValue({ data: {
			main: "main.tex", ready: true, revision: "chapter-2", pdf_available: false,
			files: [{ name: "main.tex", editable: true }], inputs: {},
			generation: { status: "running", file: "main.tex" }, compile: {},
		} });
		await vi.advanceTimersByTimeAsync(4000);
		await flushPromises();
		expect(wrapper.get("textarea").element.value).toBe("my draft");
		expect(api.getPaperSource).toHaveBeenCalledTimes(1);
		wrapper.unmount();
	});

	it("保存请求期间继续输入时，按新版本顺序保存而不丢失修改", async () => {
		let finish!: (value: unknown) => void;
		api.savePaperSource.mockReturnValueOnce(
			new Promise((resolve) => {
				finish = resolve;
			}),
		);
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		await wrapper.get("textarea").setValue("first edit");
		await vi.advanceTimersByTimeAsync(750);
		await wrapper.get("textarea").setValue("newer edit");
		finish({ data: { version: "version-2", revision: "revision-2" } });
		await flushPromises();
		expect(api.savePaperSource).toHaveBeenNthCalledWith(
			1,
			"test",
			"main.tex",
			"first edit",
			"first",
		);
		expect(api.savePaperSource).toHaveBeenNthCalledWith(
			2,
			"test",
			"main.tex",
			"newer edit",
			"version-2",
		);
		expect(wrapper.get("textarea").element.value).toBe("newer edit");
		wrapper.unmount();
	});

	it("论文手生成新文件时保留当前源码", async () => {
		const wrapper = mount(PaperEditor, { props: { task_id: "test" } });
		await flushPromises();
		const generate = wrapper
			.findAll("button")
			.find((button) => button.text() === "生成论文初稿");
		await generate?.trigger("click");
		await flushPromises();
		expect(api.generatePaper).toHaveBeenCalledWith("test");
		expect(wrapper.get("textarea").element.value).toBe("initial");
		expect(api.getPaperSource).toHaveBeenCalledTimes(1);
		wrapper.unmount();
	});
});
