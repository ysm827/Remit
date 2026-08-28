import type { OutputItem } from "./response";

type NotebookCell<Kind extends string, Body extends object> = {
	type: Kind;
} & Body;

export type CodeCell = NotebookCell<"code", { content: string }>;
export type ResultCell = NotebookCell<"result", { code_results: OutputItem[] }>;
export type NoteCell = CodeCell | ResultCell;

/** 浏览器表单维护的模型连接快照。 */
export type ModelConfig = Readonly<{
	apiKey: string;
	modelId: string;
	baseUrl: string;
	apiType: string;
	contextWindow?: number;
}>;
