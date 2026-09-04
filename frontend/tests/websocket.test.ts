import { TaskWebSocket } from "@/utils/websocket";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class BrowserSocket {
	static OPEN = 1;
	static instances: BrowserSocket[] = [];
	readyState = BrowserSocket.OPEN;
	onopen: (() => void) | null = null;
	onmessage: ((event: { data: string }) => void) | null = null;
	onclose: ((event: { code: number }) => void) | null = null;
	onerror: ((error: unknown) => void) | null = null;
	close = vi.fn();
	send = vi.fn();
	constructor(readonly url: string) {
		BrowserSocket.instances.push(this);
	}
}

beforeEach(() => {
	vi.useFakeTimers();
	BrowserSocket.instances.length = 0;
	vi.stubGlobal("WebSocket", BrowserSocket);
});
afterEach(() => {
	vi.unstubAllGlobals();
	vi.useRealTimers();
});

describe("WebSocket 连接生命周期", () => {
	it("断线后退避重连，旧连接的迟到消息和 close 事件不会影响新连接", () => {
		const receive = vi.fn();
		const status = vi.fn();
		const client = new TaskWebSocket("ws://localhost/task/A", receive, status);
		client.connect();
		const first = BrowserSocket.instances[0];
		first.onopen?.();
		first.onclose?.({ code: 1006 });
		vi.advanceTimersByTime(1000);
		const second = BrowserSocket.instances[1];
		second.onopen?.();
		first.onclose?.({ code: 1006 });
		first.onmessage?.({ data: '{"id":"old"}' });
		second.onmessage?.({ data: '{"id":"new"}' });
		expect(receive.mock.calls).toEqual([[{ id: "new" }]]);
		expect(status).toHaveBeenLastCalledWith("connected");
		vi.advanceTimersByTime(30_000);
		expect(BrowserSocket.instances).toHaveLength(2);
		client.close();
	});

	it("主动关闭会取消重连，后续事件也不会再次开启连接", () => {
		const receive = vi.fn();
		const client = new TaskWebSocket("ws://localhost/task/A", receive);
		client.connect();
		const socket = BrowserSocket.instances[0];
		socket.onclose?.({ code: 1006 });
		client.close();
		socket.onclose?.({ code: 1006 });
		socket.onmessage?.({ data: '{"id":"late"}' });
		vi.advanceTimersByTime(60_000);
		expect(receive).not.toHaveBeenCalled();
		expect(BrowserSocket.instances).toHaveLength(1);
	});

	it("异常 JSON 不打断后面的合法消息", () => {
		vi.spyOn(console, "error").mockImplementation(() => {});
		const receive = vi.fn();
		const client = new TaskWebSocket("ws://localhost/task/A", receive);
		client.connect();
		const socket = BrowserSocket.instances[0];
		expect(() => socket.onmessage?.({ data: "not-json" })).not.toThrow();
		socket.onmessage?.({ data: '{"id":"valid"}' });
		expect(receive).toHaveBeenCalledWith({ id: "valid" });
		client.close();
	});
});
