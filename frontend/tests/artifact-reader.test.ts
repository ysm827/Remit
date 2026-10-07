import "./helpers/stub-floating-panels";
import ArtifactContent from "@/pages/team/ArtifactContent.vue";
import ResultReport from "@/pages/team/ResultReport.vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

describe("项目成果阅读视图", () => {
	it("不将内部数字核对集合冒充计算依据", async () => {
		const wrapper = mount(ResultReport, {
			props: {
				result: {
					quality_report: { status: "passed" },
					coder_response: "可读计算说明",
					grounding_values: [33845, 20260928],
				},
				files: [],
			},
		});
		expect(wrapper.text()).not.toContain("33845");
		expect(wrapper.text()).not.toContain("计算依据");
		await wrapper.get(".overlay-details-trigger").trigger("click");
		expect(wrapper.text()).toContain("可读计算说明");
	});
	it("展开嵌套方案和历史JSON字符串，不丢失零值或否定结果", () => {
		const wrapper = mount(ArtifactContent, {
			props: {
				value: {
					questions_solution: {
						ques1: '{"summary":"实际结论","value":0,"passed":false}',
					},
				},
			},
		});
		expect(wrapper.text()).toContain("问题 1");
		expect(wrapper.text()).toContain("实际结论");
		expect(wrapper.text()).toContain("0");
		expect(wrapper.text()).toContain("否");
		expect(wrapper.text()).not.toContain('"summary"');
	});
	it("保留未知字段，并将记录数组显示为表格", () => {
		const wrapper = mount(ArtifactContent, {
			props: {
				value: [
					{ name: "样本一", custom_measure: 0 },
					{ name: "样本二", custom_measure: null },
				],
			},
		});
		expect(wrapper.findAll("tbody tr")).toHaveLength(2);
		expect(wrapper.text()).toContain("custom measure");
		expect(wrapper.text()).toContain("未提供");
	});
	it("长正文浮窗不扩大预览，并净化不可信HTML", async () => {
		const wrapper = mount(ArtifactContent, {
			props: {
				value: `${"正文内容".repeat(200)}<img src=x onerror=alert(1)><script>alert(1)</script>`,
			},
		});
		expect(wrapper.find("script").exists()).toBe(false);
		expect(wrapper.find("img").attributes("onerror")).toBeUndefined();
		expect(wrapper.get(".reader").classes()).toContain("clipped");
		await wrapper.get("button").trigger("click");
		expect(wrapper.get(".reader").classes()).toContain("clipped");
		expect(wrapper.get("button").attributes("aria-expanded")).toBe("true");
	});
	it("检查表明确展示未通过项和零值，图表只引用匹配的项目文件", () => {
		const wrapper = mount(ResultReport, {
			props: {
				result: {
					quality_report: {
						checks: {
							unit_consistency: { passed: false, value: 0, note: "仍有差异" },
						},
						status: "manual_review",
					},
					paper_ready_images: ["result.png", "missing.png"],
				},
				files: [{ filename: "result.png", url: "/safe/result.png" }],
			},
		});
		expect(wrapper.get("tbody").text()).toContain("未通过");
		expect(wrapper.get("tbody").text()).toContain("0");
		expect(wrapper.text()).toContain("报告建议人工复核");
		expect(wrapper.findAll("img")).toHaveLength(1);
		expect(wrapper.get("img").attributes("src")).toBe("/safe/result.png");
	});
});
