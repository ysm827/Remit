/** Storage can be denied or full in WebView; it must not break navigation or sending. */
export function readBrowserStorage(
	kind: "localStorage" | "sessionStorage",
	key: string,
): string | null {
	try {
		return window[kind].getItem(key);
	} catch {
		return null;
	}
}

export function writeBrowserStorage(
	kind: "localStorage" | "sessionStorage",
	key: string,
	value: string | null,
): boolean {
	try {
		if (value === null) window[kind].removeItem(key);
		else window[kind].setItem(key, value);
		return true;
	} catch {
		return false;
	}
}
