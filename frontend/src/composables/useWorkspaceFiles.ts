import {
	type WorkspaceFile,
	getAllFilesDownloadUrl,
	getFileDownloadUrl,
	getFiles,
} from "@/apis/filesApi";
import { computed, ref } from "vue";

type Notice = (
	title: string,
	description: string,
	destructive?: boolean,
) => void;

const readableSize = new Intl.NumberFormat("zh-CN", {
	maximumFractionDigits: 1,
});

function startDownload(url: string, filename: string): void {
	const link = Object.assign(document.createElement("a"), {
		href: url,
		download: filename,
	});
	link.rel = "noopener";
	link.click();
}

export function useWorkspaceFiles(taskId: string, notice: Notice) {
	const files = ref<WorkspaceFile[]>([]);
	const busy = ref<"listing" | "archive" | string | null>(null);
	const isListing = computed(() => busy.value === "listing");
	const isArchiving = computed(() => busy.value === "archive");

	const filename = (file: WorkspaceFile) => file.name || file.filename;
	const fileSize = (file: WorkspaceFile) => {
		if (!file.size) return "";
		const units = ["B", "KB", "MB", "GB"];
		let scaled = file.size;
		let unitIndex = 0;
		while (scaled >= 1024 && unitIndex < units.length - 1) {
			scaled /= 1024;
			unitIndex += 1;
		}
		return `${readableSize.format(scaled)} ${units[unitIndex]}`;
	};

	async function refresh(): Promise<boolean> {
		busy.value = "listing";
		try {
			const response = await getFiles(taskId);
			files.value = Array.isArray(response.data) ? response.data : [];
			return true;
		} catch (error) {
			console.error("workspace listing failed", error);
			notice("无法读取工作区", "请确认任务仍然存在，然后重试。", true);
			return false;
		} finally {
			busy.value = null;
		}
	}

	async function download(file?: WorkspaceFile): Promise<void> {
		const name = file ? filename(file) : `remit-${taskId}-artifacts.zip`;
		busy.value = file ? name : "archive";
		try {
			const response = file
				? await getFileDownloadUrl(taskId, name)
				: await getAllFilesDownloadUrl(taskId);
			const url = response.data?.download_url;
			if (!url) throw new Error("download endpoint returned no URL");
			startDownload(url, name);
			notice("下载已开始", file ? name : "工作区压缩包");
		} catch (error) {
			console.error("workspace download failed", error);
			notice("下载失败", `暂时无法下载 ${name}`, true);
		} finally {
			busy.value = null;
		}
	}

	return {
		files,
		busy,
		isListing,
		isArchiving,
		filename,
		fileSize,
		refresh,
		download,
	};
}
