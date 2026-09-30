import request from "@/utils/request";

export interface CompileResult {
	page_count?: number;
	status?: string;
	revision?: string;
	pdf_revision?: string;
	at?: string;
	log?: string;
	diagnostics?: { file: string; line: number; message: string }[];
	layout_review?: { status: string; issues: string[]; metrics?: { abstract_page_fill?: number }; manual_checks?: string[] };
}
export interface PaperWorkspace {
	main: string;
	ready: boolean;
	modeling_status: string;
	revision: string;
	pdf_available: boolean;
	compiling: boolean;
	files: { name: string; editable: boolean }[];
	inputs: {
		revision?: string;
		synced_at?: string;
		sections?: string[];
		asset_count?: number;
	};
	generation: {
		status: string;
		section?: string;
		file?: string;
		partial?: boolean;
		completed_sections?: string[];
		error?: string;
		message?: string;
	};
	compile: CompileResult;
}
export interface WritingProject {
	task_id: string;
	title: string;
	ready: boolean;
	status: string;
	sections: number;
	synced_at?: string;
}
export const writingUrl = (id: string, path = "") =>
	`${request.defaults.baseURL}/api/writing/${encodeURIComponent(id)}${path}`;
export const getWritingProjects = () =>
	request.get<WritingProject[]>("/api/writing/projects");
export const getPaperWorkspace = (id: string) =>
	request.get<PaperWorkspace>(`/api/writing/${id}`);
export const getPaperSource = (id: string, name: string) =>
	request.get<{ content: string; version: string }>(
		`/api/writing/${id}/source`,
		{
			params: { name },
		},
	);
export const savePaperSource = (
	id: string,
	name: string,
	content: string,
	version: string | null,
) =>
	request.post<{ version: string; revision: string }>(
		`/api/writing/${id}/source`,
		{
			name,
			content,
			version,
		},
	);
export const compilePaper = (id: string) =>
	request.post<CompileResult>(
		`/api/writing/${id}/compile`,
		{},
		{ timeout: 200000 },
	);
export const syncPaper = (id: string) =>
	request.post(`/api/writing/${id}/sync`);
export const generatePaper = (id: string) =>
	request.post(`/api/writing/${id}/generate`);
export const cancelPaper = (id: string) =>
	request.post(`/api/writing/${id}/cancel`);
export const setPaperMain = (id: string, name: string) =>
	request.post(`/api/writing/${id}/main`, { name });
export const getPaperHistory = (id: string, name: string) =>
	request.get<{ content: string; saved_at: string }[]>(
		`/api/writing/${id}/history`,
		{ params: { name } },
	);
