import { useTeamStream } from "@/pages/team/useTeamStream";
import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class Stream {
	static latest: Stream;
	static CLOSED = 2;
	readyState = 0;
	onopen: (() => void) | null = null;
	onerror: (() => void) | null = null;
	onmessage: ((event: { data: string }) => void) | null = null;
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
	task_id: "test",
	title: "项目",
	status: "chat",
	steps: [],
	commands: [],
	writing: {},
	sequence: 2,
};
const event = {
	seq: 1,
	at: "2026-10-07",
	role: "coder",
	kind: "reply",
	content: "已完成",
	data: {},
};

describe("实时连接生命周期", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.stubGlobal("EventSource", Stream);
	});
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});
	function setup() {
		const scope = effectScope();
		const apply = vi.fn();
		const deleted = vi.fn();
		const api = scope.run(() => useTeamStream(apply, deleted));
		if (!api) throw new Error("Failed to create stream scope");
		api.open("test");
		return { scope, apply, deleted, api, stream: Stream.latest };
	}
	it("连续重试不会推迟断线提醒，恢复后清除所有断线计时器", async () => {
		const { scope, api, stream } = setup();
		try {
			stream.onerror?.();
			await vi.advanceTimersByTimeAsync(3000);
			stream.onerror?.();
			await vi.advanceTimersByTimeAsync(1100);
			expect(api.connection.value).toContain("正在自动重连");
			stream.onerror?.();
			await vi.advanceTimersByTimeAsync(30000);
			expect(api.connection.value).toContain("同步仍未恢复");
			stream.onopen?.();
			expect(api.connection.value).toBe("已重新连接");
			await vi.advanceTimersByTimeAsync(35000);
			expect(api.connection.value).toBe("实时同步");
		} finally {
			scope.stop();
		}
	});
	it("异常与串项目消息不污染缓冲，下一条有效消息恢复同步", () => {
		const { scope, api, apply, stream } = setup();
		try {
			stream.update({ state, events: [event] });
			stream.update({
				state: { ...state, steps: null },
				events: [{ ...event, seq: 2 }],
			});
			stream.update({
				state: { ...state, task_id: "other" },
				events: [{ ...event, seq: 3 }],
			});
			expect(apply).not.toHaveBeenCalled();
			expect(api.connection.value).toContain("数据异常");
			stream.update({ state, events: [{ ...event, seq: 2 }] });
			expect(apply).toHaveBeenCalledExactlyOnceWith(
				[event, { ...event, seq: 2 }],
				state,
			);
			expect(api.connection.value).toBe("实时同步");
		} finally {
			scope.stop();
		}
	});
	it("离开页面后取消待发布事件，并忽略迟到的连接回调", async () => {
		const { scope, api, apply, stream } = setup();
		stream.update({ state, events: [event] });
		stream.onerror?.();
		scope.stop();
		const previous = api.connection.value;
		stream.onopen?.();
		stream.update({ state, events: [{ ...event, seq: 2 }] });
		await vi.advanceTimersByTimeAsync(40000);
		expect(stream.close).toHaveBeenCalledOnce();
		expect(apply).not.toHaveBeenCalled();
		expect(api.connection.value).toBe(previous);
		expect(vi.getTimerCount()).toBe(0);
	});
	it("替换连接后旧消息和删除事件不会改变新项目", () => {
		const { scope, api, apply, deleted, stream } = setup();
		try {
			api.open("other");
			stream.update({ state, events: [{ ...event, seq: 2 }] });
			stream.addEventListener.mock.calls[0][1]();
			expect(apply).not.toHaveBeenCalled();
			expect(deleted).not.toHaveBeenCalled();
			expect(stream.close).toHaveBeenCalledOnce();
		} finally {
			scope.stop();
		}
	});
});
