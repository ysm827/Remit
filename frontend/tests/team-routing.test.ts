import router from "@/router";
import { describe, expect, it } from "vitest";

describe("团队工作区路由", () => {
	it("默认项目进入对话，成果详情仍有独立入口", () => {
		expect(router.resolve("/project/example").matched.at(-1)?.path).toBe(
			"/project/:projectId",
		);
		expect(
			router.resolve("/project/example/overview").matched.at(-1)?.path,
		).toBe("/project/:projectId/:stage");
		expect(router.resolve("/task/example").matched.at(-1)?.path).toBe(
			"/task/:task_id",
		);
	});
});
