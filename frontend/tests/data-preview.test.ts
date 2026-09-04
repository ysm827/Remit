import ProjectDataView from "@/pages/task/components/ProjectDataView.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getFiles: vi.fn(), previewCsv: vi.fn() }));
vi.mock("@/apis/filesApi", () => api);

describe("数据预览选择", () => {
	it("快速选择 B 后，A 的迟到响应不会显示在 B 文件名下", async () => {
		let finishA!: (value: unknown) => void;
		const old = new Promise((resolve) => {
			finishA = resolve;
		});
		api.getFiles.mockResolvedValue({
			data: [
				{ filename: "A.csv", file_type: "csv" },
				{ filename: "B.csv", file_type: "csv" },
			],
		});
		api.previewCsv.mockReturnValueOnce(old).mockResolvedValueOnce({
			data: {
				columns: ["value"],
				rows: [{ value: "B-content" }],
				truncated: false,
			},
		});
		const wrapper = mount(ProjectDataView, { props: { taskId: "A" } });
		await flushPromises();
		const button = wrapper
			.findAll("button")
			.find((item) => item.text().includes("B.csv"));
		expect(button).toBeDefined();
		await button?.trigger("click");
		await flushPromises();
		finishA({
			data: {
				columns: ["value"],
				rows: [{ value: "A-content" }],
				truncated: false,
			},
		});
		await flushPromises();
		expect(wrapper.text()).toContain("正在查看 B.csv");
		expect(wrapper.text()).toContain("B-content");
		expect(wrapper.text()).not.toContain("A-content");
		wrapper.unmount();
	});
});
