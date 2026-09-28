import request from "@/utils/request";
import type { ApprovalMessage } from "@/utils/response";
import type { ModelingSubmission } from "./submitModelingApi";

export interface ProjectEntry {
	task_id: string;
	title: string;
	status: string;
	archived: boolean;
	updated_at: string;
}
export interface PaperContext {
	name: string;
	version: string | null;
	start: number;
	end: number;
}
export interface PaperProposal {
	id: string;
	name: string;
	summary: string;
	diff: string;
	status: string;
}
export function getProjects() {
	return request.get<ProjectEntry[]>("/api/projects");
}
/** 保留文件夹层级，避免不同子目录的同名文件被压平。 */
function appendAttachments(form: FormData, files: File[]) {
	for (const file of files) form.append("files", file);
	form.append(
		"relative_paths",
		JSON.stringify(files.map((file) => file.webkitRelativePath || file.name)),
	);
}
export function uploadProjectAttachments(
	id: string,
	files: File[],
	documentText = "",
	onProgress?: (percent: number) => void,
) {
	const form = new FormData();
	appendAttachments(form, files);
	if (documentText) form.append("document_text", documentText);
	return request.post(
		`/api/projects/${encodeURIComponent(id)}/attachments`,
		form,
		{
			timeout: 300000,
			onUploadProgress: (event) =>
				onProgress?.(Math.round((event.progress || 0) * 100)),
		},
	);
}
export function updateProject(
	id: string,
	body: { title?: string; archived?: boolean },
) {
	return request.patch(`/api/projects/${encodeURIComponent(id)}`, body);
}
/** 用户确认后永久删除归档项目及其文件。 */
export function deleteProject(id: string) {
	return request.delete(`/api/projects/${encodeURIComponent(id)}`, {
		data: { confirmed: true },
	});
}
export function prepareProject(
	problem: ModelingSubmission & {
		competition_id?: string;
		competition_year?: string;
		paper_language?: string;
		competition_requirements?: string;
	},
	files: File[],
) {
	const form = new FormData();
	for (const [key, value] of Object.entries(problem))
		if (value !== undefined) form.append(key, value);
	appendAttachments(form, files);
	return request.post<{ task_id: string }>("/api/projects", form, {
		timeout: 300000,
	});
}
export function getPaperProposals(id: string) {
	return request.get<PaperProposal[]>(
		`/api/writing/${encodeURIComponent(id)}/proposals`,
	);
}
export function decidePaperProposal(
	id: string,
	proposalId: string,
	accept: boolean,
) {
	return request.post<{ status: string; compile?: string; error?: string }>(
		`/api/writing/${encodeURIComponent(id)}/proposals/${proposalId}`,
		{ accept },
		{ timeout: 240000 },
	);
}

export interface TeamEvent {
	seq: number;
	event_key?: string;
	at: string;
	role: string;
	kind: string;
	content: string;
	data: Record<string, unknown>;
}
export interface CompetitionProfile {
	id: string;
	name: string;
	language: string;
	year: number;
	rules_status: string;
	focus: string;
	rules: Record<string, unknown>;
	review_items: string[];
	sources: { url: string; label: string }[];
	event_note?: string;
}
export function getCompetitions() {
	return request.get<CompetitionProfile[]>("/api/competitions");
}
export interface TeamStep {
	id: string;
	label: string;
	role: string;
	status: string;
	issues?: string[];
}
export interface TeamState {
	task_id: string;
	title: string;
	status: string;
	current_node: string | null;
	archived?: boolean;
	preflight?: {
		id: string;
		understanding: string;
		steps: string[];
		questions: string[];
		attachments: { file: string; status: string }[];
	};
	sequence: number;
	commands: { id: string; status: string }[];
	steps: TeamStep[];
	pending_approval: ApprovalMessage | null;
	directives: { id: string; role: string; content: string; seen: string[] }[];
	writing: { status?: string; file?: string; error?: string };
}
export type TeamAction =
	| "approve"
	| "stop"
	| "resume"
	| "write"
	| "stop_writing"
	| "compile"
	| "start"
	| "edit_paper";
export function getTeamState(id: string) {
	return request.get<TeamState>(`/api/team/${encodeURIComponent(id)}`);
}
export function sendTeamMessage(
	id: string,
	body: {
		request_id: string;
		content: string;
		checkpoint_id?: string;
		plan_id?: string;
		paper_context?: PaperContext;
		timing?: "immediate" | "after_step";
		conversation_only?: boolean;
		role?: string;
		action?: TeamAction;
	},
) {
	return request.post(`/api/team/${encodeURIComponent(id)}/messages`, body);
}
export function teamStreamUrl(id: string, after = 0) {
	return `${request.defaults.baseURL}/api/team/${encodeURIComponent(id)}/stream?after=${after}`;
}

/** 重连可能重放最后一帧，只按服务器单调序号合并。 */
export function mergeTeamEvents(current: TeamEvent[], incoming: TeamEvent[]) {
	const entries = new Map(current.map((event) => [event.seq, event]));
	for (const event of incoming) entries.set(event.seq, event);
	return [...entries.values()].sort((a, b) => a.seq - b.seq);
}
