(() => {
	const id = Date.now().toString(36),
		samples = [],
		snapshots = [],
		longTasks = [],
		layoutReads = [],
		streamBatches = [],
		navigationReady = [],
		received = {},
		activeStreams = new Set(),
		activeIntervals = new Set();
	let phase = "warmup",
		latestKey = null;
	let navigation = null;
	document.addEventListener(
		"click",
		(event) => {
			const link = event.target?.closest?.('a[href^="/project/"]');
			if (link)
				navigation = {
					path: new URL(link.href).pathname,
					start: performance.now(),
					phase,
				};
		},
		true,
	);
	new MutationObserver(() => {
		const pending = navigation;
		if (!pending || location.pathname !== pending.path) return;
		// Fixture milestone: final non-system reply is in the mounted conversation.
		const messages = document.querySelectorAll(".event-content");
		if (!messages[messages.length - 1]?.textContent?.includes("夹具事件 1999"))
			return;
		navigation = null;
		requestAnimationFrame(() =>
			requestAnimationFrame(() =>
				navigationReady.push({
					path: pending.path,
					phase: pending.phase,
					ms: performance.now() - pending.start,
				}),
			),
		);
	}).observe(document, { childList: true, subtree: true });
	// Diagnostic-only wrapper: attribute forced layout to the conversation scroll.
	const scrollHeight = Object.getOwnPropertyDescriptor(
		Element.prototype,
		"scrollHeight",
	);
	if (scrollHeight?.get) {
		Object.defineProperty(Element.prototype, "scrollHeight", {
			...scrollHeight,
			get() {
				const start = performance.now();
				const height = scrollHeight.get.call(this);
				if (this.classList.contains("conversation-scroll"))
					layoutReads.push({
						phase,
						at: start,
						ms: performance.now() - start,
						height,
					});
				return height;
			},
		});
	}
	const NativeEventSource = window.EventSource;
	window.EventSource = class extends NativeEventSource {
		constructor(...args) {
			super(...args);
			activeStreams.add(this);
			this.addEventListener("message", (event) => {
				try {
					const data = JSON.parse(event.data);
					const key = new URL(this.url).pathname;
					const values = (received[key] ||= new Set());
					for (const item of data.events || []) values.add(item.seq);
					if (data.events?.length) {
						const start = performance.now(),
							capturedPhase = phase;
						requestAnimationFrame(() =>
							requestAnimationFrame(() =>
								streamBatches.push({
									phase: capturedPhase,
									path: key,
									count: data.events.length,
									lastSeq: data.events.at(-1)?.seq,
									ms: performance.now() - start,
								}),
							),
						);
					}
				} catch {}
			});
		}
		close() {
			activeStreams.delete(this);
			return super.close();
		}
	};
	const nativeSet = window.setInterval.bind(window),
		nativeClear = window.clearInterval.bind(window);
	window.setInterval = (...args) => {
		const value = nativeSet(...args);
		activeIntervals.add(value);
		return value;
	};
	window.clearInterval = (value) => {
		activeIntervals.delete(value);
		return nativeClear(value);
	};
	try {
		new PerformanceObserver((list) => {
			for (const e of list.getEntries())
				longTasks.push({ start: e.startTime, duration: e.duration, phase });
		}).observe({ entryTypes: ["longtask"] });
	} catch {}
	const ignored = (target) => target?.closest?.("[data-perf-controls]");
	document.addEventListener(
		"keydown",
		(e) => {
			if (!ignored(e.target))
				latestKey = { target: e.target, time: e.timeStamp };
		},
		true,
	);
	for (const kind of ["input", "click", "change", "scroll"])
		document.addEventListener(
			kind,
			(event) => {
				if (ignored(event.target) || phase === "warmup") return;
				const t = event.target,
					start =
						kind === "input" &&
						latestKey?.target === t &&
						event.timeStamp - latestKey.time < 500
							? latestKey.time
							: event.timeStamp;
				const capturedPhase = phase,
					label =
						t?.getAttribute?.("aria-label") ||
						t?.closest?.("button,a")?.textContent?.slice(0, 60) ||
						t?.className ||
						kind;
				requestAnimationFrame(() =>
					requestAnimationFrame(() =>
						samples.push({
							phase: capturedPhase,
							kind,
							ms: performance.now() - start,
							trusted: event.isTrusted,
							label: String(label).slice(0, 80),
							length: t?.value?.length ?? null,
							path: location.pathname + location.search,
						}),
					),
				);
			},
			{ capture: true, passive: true },
		);
	function snapshot() {
		const memory = performance.memory;
		return {
			phase,
			at: performance.now(),
			path: location.pathname + location.search,
			jsHeapUsed: memory?.usedJSHeapSize ?? null,
			jsHeapTotal: memory?.totalJSHeapSize ?? null,
			domNodes: document.querySelectorAll("*").length,
			images: [...document.images].map((i) => ({
				loaded: i.complete && i.naturalWidth > 0,
				width: i.naturalWidth,
				height: i.naturalHeight,
			})),
			activeStreams: activeStreams.size,
			activeIntervals: activeIntervals.size,
			sourceLength: document.querySelector(".code-input")?.value.length ?? null,
			visibility: document.visibilityState,
		};
	}
	document.addEventListener("DOMContentLoaded", () => {
		const panel = document.createElement("div");
		panel.dataset.perfControls = "";
		panel.style.cssText =
			"position:fixed;bottom:1px;left:1px;z-index:99999;padding:5px;background:#fff8cf;border:1px solid #aaa;font:11px sans-serif";
		panel.innerHTML =
			'<select aria-label="测量场景"><option>warmup</option><option>input-chat</option><option>input-paper</option><option>interactions</option><option>switching</option><option>scroll</option><option>finish</option></select> <button>保存测量快照</button><output aria-label="测量状态">待测量</output>';
		const select = panel.querySelector("select"),
			output = panel.querySelector("output");
		select.addEventListener("change", () => {
			phase = select.value;
		});
		panel.querySelector("button").addEventListener("click", async () => {
			snapshots.push(snapshot());
			const response = await fetch("/__perf/report", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					id,
					userAgent: navigator.userAgent,
					viewport: {
						width: innerWidth,
						height: innerHeight,
						dpr: devicePixelRatio,
					},
					hardwareConcurrency: navigator.hardwareConcurrency,
					deviceMemory: navigator.deviceMemory ?? null,
					samples,
					snapshots,
					longTasks,
					layoutReads,
					streamBatches,
					navigationReady,
					received: Object.fromEntries(
						Object.entries(received).map(([key, values]) => [
							key,
							[...values].sort((a, b) => a - b),
						]),
					),
				}),
			});
			output.textContent = response.ok
				? "已保存 " + samples.length + " 个样本"
				: "保存失败";
		});
		document.body.append(panel);
	});
})();
