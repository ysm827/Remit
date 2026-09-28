import { prepareProject, uploadProjectAttachments } from "@/apis/teamApi";
import request from "@/utils/request";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/utils/request", () => ({
	default: { post: vi.fn().mockResolvedValue({ data: {} }) },
}));

describe("文件夹上传协议", () => {
	it("新项目和后续附件都携带相对路径，文件名保持兼容", async () => {
		const file = new File(["x\n1"], "data.csv");
		Object.defineProperty(file, "webkitRelativePath", {
			value: "数据/sub/data.csv",
		});
		await prepareProject({ ques_all: "检查数据" }, [file]);
		await uploadProjectAttachments("project-1", [file], "赛题原文");
		const calls = vi.mocked(request.post).mock.calls;
		for (const call of calls) {
			const form = call[1] as FormData;
			expect(JSON.parse(String(form.get("relative_paths")))).toEqual([
				"数据/sub/data.csv",
			]);
			expect((form.get("files") as File).name).toBe("data.csv");
		}
		expect((calls[1][1] as FormData).get("document_text")).toBe("赛题原文");
	});
});
