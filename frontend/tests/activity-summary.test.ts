import type { TeamEvent, TeamState } from "@/apis/teamApi";
import ActivitySummary from "@/pages/team/ActivitySummary.vue";
import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";

const event = (
	seq: number,
	content: string,
	kind = "activity",
	data = {},
): TeamEvent => ({
	seq,
	content,
	kind,
	data,
	role: "coder",
	at: "2026-09-28T02:00:00Z",
});
it("数百条心跳只显示当前进度，原始日志延迟加载且分页", async () => {
	const events = Array.from({ length: 390 }, (_, i) =>
		event(i, "代码手正在输出…"),
	);
	events.push(
		event(391, "正在校验第一问的交付质量"),
		event(392, "execute_code", "tool", { input: { code: "sensitive-debug" } }),
	);
	const wrapper = mount(ActivitySummary, { props: { events } });
	expect(wrapper.text()).toContain("正在校验第一问");
	expect(wrapper.text()).not.toContain("390");
	expect(wrapper.findAll(".activity-entry")).toHaveLength(0);
	expect(wrapper.text()).not.toContain("sensitive-debug");
	const raw = wrapper.get(".raw-log");
	(raw.element as HTMLDetailsElement).open = true;
	await raw.trigger("toggle");
	expect(wrapper.findAll(".activity-entry")).toHaveLength(30);
	expect(wrapper.text()).toContain("sensitive-debug");
	await wrapper.get(".raw-log button").trigger("click");
	expect(wrapper.findAll(".activity-entry")).toHaveLength(80);
});
it("失败与恢复都保留，摘要不把工具成功当作任务完成", () => {
	const wrapper = mount(ActivitySummary, {
		props: {
			events: [
				event(1, "MATLAB 代码执行失败", "system"),
				event(2, "代码报错，正在自动修复（1/3）"),
				event(3, "代码执行成功，继续下一步"),
				event(4, "代码手正在输出…"),
			],
		},
	});
	expect(wrapper.get(".progress-label").text()).toBe(
		"代码执行成功，继续下一步",
	);
	expect(wrapper.text()).toContain("MATLAB 代码执行失败");
	expect(wrapper.text()).toContain("自动修复 1 次");
	expect(wrapper.text()).not.toContain("任务完成");
});

const snapshot: TeamState = {
	task_id: 'test', title: '运输优化', status: 'running', current_node: 'modeler', sequence: 400,
	commands: [], directives: [], writing: {}, pending_approval: null,
	steps: [
		{ id: 'coordinator', label: '题意识别与问题拆解', role: 'coordinator', status: 'completed' },
		{ id: 'analysis', label: '题目理解与数据核验', role: 'modeler', status: 'warning', issues: ['4 个附件尚未完整读取'] },
		{ id: 'modeler', label: '总体建模方案', role: 'modeler', status: 'running' },
	],
};
it('跳过的探索不进入最近完成，并一直保留未验证提醒', () => {
 const state = { ...snapshot, steps: [
  { id: 'pilot', label: '候选探索', role: 'coder', status: 'skipped', issues: ['候选结果不完整，沿用原方案'] },
  { id: 'solve:ques1', label: '第一问', role: 'coder', status: 'running' },
 ], current_node: 'solve:ques1' };
 const wrapper = mount(ActivitySummary, { props: { events: [], state } });
 expect(wrapper.get('.warning-note').text()).toContain('已跳过，未验证');
 expect(wrapper.get('.warning-note').text()).toContain('沿用原方案');
 expect(wrapper.text()).not.toContain('最近完成');
});
it('默认展示阶段、已完成与未核验项，心跳不会挤掉关键结果', () => {
	const events = [event(1, '调研结果：检索 24 篇文献，精读 1 篇'), event(2, '已生成 4 问分析，但证据核验尚未完整'),
		...Array.from({length: 390}, (_, i) => event(i + 3, '协调手正在输出…'))];
	const wrapper = mount(ActivitySummary, { props: { events, state: snapshot } });
	expect(wrapper.get('.progress-label').text()).toBe('总体建模方案');
	expect(wrapper.get('.progress-role').text()).toBe('建模手');
	expect(wrapper.get('.completed-line').text()).toContain('题意识别与问题拆解');
	expect(wrapper.get('.completed-line').text()).not.toContain('数据核验');
	expect(wrapper.get('.warning-note').text()).toContain('仍需核验');
	expect(wrapper.get('.milestones').text()).toContain('检索 24 篇文献');
	expect(wrapper.get('.milestones').element.closest('details')).toBeNull();
	expect(wrapper.findAll('.activity-entry')).toHaveLength(0);
	expect(wrapper.text()).not.toContain('390');
});
it('重试和待验收立即可见，并且不会把工具成功当成果完成', async () => {
	const wrapper = mount(ActivitySummary, { props: { events: [event(1, '模型回复不完整，正在重新生成（1/1）')], state: snapshot } });
	expect(wrapper.get('.current-line').text()).toContain('正在重新生成');
	await wrapper.setProps({ state: { ...snapshot, status: 'awaiting_approval', steps: snapshot.steps.map(s => s.id === 'modeler' ? {...s, status: 'awaiting_approval'} : s) } });
	expect(wrapper.get('.attention-note').text()).toContain('等待你的验收');
	expect(wrapper.get('.completed-line').text()).not.toContain('总体建模方案');
});
it('用简短行动说明解释当前工作，新的执行限制不能被旧说明覆盖', async () => {
	const events = [
		{ ...event(1, '继续检查地理数据的字段与行数。', 'agent'), role: 'modeler' },
		event(2, '内部思考过程', 'agent'),
		event(3, '代码执行成功，继续下一步'),
		event(4, '代码手正在思考下一步（eda 第 10 轮）'),
	];
	const wrapper = mount(ActivitySummary, { props: { events, state: snapshot } });
	expect(wrapper.get('.current-line').text()).toContain('继续检查地理数据的字段与行数');
	expect(wrapper.text()).not.toContain('内部思考过程');
	expect(wrapper.text()).not.toContain('eda');
	await wrapper.setProps({ events: [...events, event(5, 'eda 已达到代码执行上限，正在整理已有结果')] });
	expect(wrapper.get('.current-line').text()).toContain('已达到代码执行上限');
	expect(wrapper.get('.current-line').text()).not.toContain('继续检查');
});
