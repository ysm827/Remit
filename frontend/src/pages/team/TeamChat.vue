<script setup lang="ts">
import {
	type ExecutionBackend,
	explainModelingSubmissionFailure,
} from "@/apis/submitModelingApi";
import {
	type CompetitionProfile,
	type PaperContext,
	type PaperProposal,
	type ProjectEntry,
	type TeamAction,
	type TeamEvent,
	type TeamState,
	decidePaperProposal,
	deleteProject,
	getCompetitions,
	getPaperProposals,
	getProjects,
	getTeamState,
	mergeTeamEvents,
	prepareProject,
	sendTeamMessage,
	teamStreamUrl,
	updateProject,
	uploadProjectAttachments,
} from "@/apis/teamApi";
import ProblemPdfDropzone from "@/components/ProblemPdfDropzone.vue";
import ApiDialog from "@/pages/chat/components/ApiDialog.vue";
import HumanApprovalCard from "@/pages/team/HumanApprovalCard.vue";
import PaperEditor from "@/pages/writing/PaperEditor.vue";
import { renderMarkdown } from "@/utils/markdown";
import { onClickOutside, useMediaQuery } from "@vueuse/core";
import {
	ArrowUp,
	Check,
	Copy,
	FileText,
	FolderOpen,
	ListChecks,
	LoaderCircle,
	MessageSquare,
	MoreHorizontal,
	PanelLeft,
	Paperclip,
	Plus,
	Settings2,
	Square,
	X,
} from "lucide-vue-next";
import {
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogOverlay,
	AlertDialogRoot,
	AlertDialogTitle,
} from "reka-ui";
import {
	computed,
	nextTick,
	onBeforeUnmount,
	onMounted,
	ref,
	watch,
} from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import ActivitySummary from "./ActivitySummary.vue";
import RoleAvatar from "./RoleAvatar.vue";
import RemitWelcome from "./RemitWelcome.vue";
import { roleLabels as labels } from "./roles";
import ProjectFiles from "./ProjectFiles.vue";
import UserMessage from "./UserMessage.vue";

const props = defineProps<{ task_id?: string }>();
const approvalExplanationRequest =
	"请用第一次参加数模比赛的人也能听懂的话解释当前成果。用约200至400字说清：现在做了什么、哪些还没做、最重要的1至2个风险、点批准后会做什么以及你的建议。风险请用这道题的具体例子解释，不要堆算法缩写、内部状态或文件名。如果还没计算，直接说明目前只有方案、效果尚未验证。只解释，不批准、不启动或重做任务。";
const PaperEditorView = PaperEditor;
const competitions = ref<CompetitionProfile[]>([]);
const competitionId = ref("cumcm");
const competitionYear = ref(2026);
const paperLanguage = ref("");
const competitionRequirements = ref("");
const contestOptionsOpen = ref(false);
const selectedCompetition = computed(() =>
	competitions.value.find((item) => item.id === competitionId.value),
);
const router = useRouter();
const history = ref<ProjectEntry[]>([]);
const route = useRoute();
const view = computed(() =>
	route.query.view === "paper"
		? "paper"
		: route.query.view === "files"
			? "files"
			: "chat",
);
const paperOpened = ref(view.value === "paper");
const paperEditor = ref<InstanceType<typeof PaperEditor> | null>(null);
const chatOpen = ref(false);
const editPaper = ref(true);
const proposals = ref<PaperProposal[]>([]);
const deciding = ref("");
const showArchived = ref(false);
const projectMenu = ref("");
const renameId = ref("");
const renameText = ref("");
const deleteTarget = ref<ProjectEntry | null>(null);
const deleting = ref(false);
const deleteError = ref("");
function requestDelete(project: ProjectEntry) {
	deleteTarget.value = project;
	deleteError.value = "";
	projectMenu.value = "";
}
function closeDelete(open: boolean) {
	if (!open && !deleting.value) deleteTarget.value = null;
}
async function confirmDelete() {
	const project = deleteTarget.value;
	if (!project || deleting.value) return;
	deleting.value = true;
	deleteError.value = "";
	try {
		await deleteProject(project.task_id);
		history.value = history.value.filter(
			(item) => item.task_id !== project.task_id,
		);
		sessionStorage.removeItem(`team-draft:${project.task_id}`);
		deleteTarget.value = null;
		if (project.task_id === props.task_id) {
			stream?.close();
			await router.push("/home");
		}
	} catch (cause) {
		deleteError.value = explainModelingSubmissionFailure(cause);
	} finally {
		deleting.value = false;
	}
}
const attachmentMenu = ref(false);
const showDetails = ref(false);
const optionsOpen = ref(false);
const displayOptions = ref<HTMLElement | null>(null);
onClickOutside(
	displayOptions,
	() => {
		optionsOpen.value = false;
	},
	{ ignore: ['[aria-label="对话显示选项"]'] },
);
const copied = ref<number | null>(null);
const composerInput = ref<HTMLTextAreaElement | null>(null);
const adjustmentOpen = ref(false);
type Adjustment = "immediate" | "after_step";
async function copyReply(event: TeamEvent) {
	try {
		await navigator.clipboard.writeText(event.content);
		copied.value = event.seq;
	} catch {
		error.value = "复制失败，请选择文字后复制。";
	}
}
watch(view, (value) => {
	if (value === "paper") {
		paperOpened.value = true;
		boardOpen.value = false;
	}
});
async function changeView(value: string) {
	await router.push({
		path: `/project/${props.task_id}`,
		query: value === "chat" ? {} : { view: value },
	});
}
async function manageProject(project: ProjectEntry, archive: boolean) {
	try {
		await updateProject(project.task_id, { archived: archive });
		projectMenu.value = "";
		await loadHistory();
		if (project.task_id === props.task_id) await refreshState();
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
	}
}
async function renameProject() {
	try {
		await updateProject(renameId.value, { title: renameText.value });
		renameId.value = "";
		await loadHistory();
		if (props.task_id) await refreshState();
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
	}
}
async function refreshProposals() {
	if (props.task_id)
		proposals.value = (await getPaperProposals(props.task_id)).data;
}
async function decideProposal(proposal: PaperProposal, accept: boolean) {
	if (!props.task_id || deciding.value) return;
	deciding.value = proposal.id;
	try {
		if (accept && paperEditor.value && !(await paperEditor.value.save()))
			throw new Error("源码有未保存修改，请先处理保存冲突。");
		const result = (
			await decidePaperProposal(props.task_id, proposal.id, accept)
		).data;
		if (accept) await paperEditor.value?.reloadAccepted();
		await refreshProposals();
		if (result.compile === "failed")
			error.value = "修改已保存，编译未通过，请查看论文编辑器中的日志。";
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
	} finally {
		deciding.value = "";
	}
}
const historyError = ref("");
const search = ref("");
const state = ref<TeamState | null>(null);
const events = ref<TeamEvent[]>([]);
const draft = ref("");
const sending = ref(false);
const error = ref("");
const connection = ref("连接中");
const settingsOpen = ref(false);
const sidebarOpen = ref(false);
const narrowScreen = useMediaQuery("(max-width: 850px)");
const sidebarCollapsed = ref(
	localStorage.getItem("remit-sidebar-collapsed") === "true",
);
const sidebarVisible = computed(() =>
	narrowScreen.value ? sidebarOpen.value : !sidebarCollapsed.value,
);
function toggleSidebar() {
	if (narrowScreen.value) sidebarOpen.value = !sidebarOpen.value;
	else {
		sidebarCollapsed.value = !sidebarCollapsed.value;
		localStorage.setItem(
			"remit-sidebar-collapsed",
			String(sidebarCollapsed.value),
		);
	}
}
const boardOpen = ref(false);
const uploadsOpen = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const uploadProgress = ref<number | null>(null);
const attachmentNotice = ref("");
const attachments = ref<File[]>([]);
const attachmentGroups = computed(() => {
	const groups = new Map<
		string,
		{ key: string; label: string; count: number; folder: boolean }
	>();
	for (const file of attachments.value) {
		const folder = !!file.webkitRelativePath;
		const label = folder ? file.webkitRelativePath.split("/")[0] : file.name;
		const key = `${folder ? "folder" : "file"}:${label}`;
		const group = groups.get(key) || { key, label, count: 0, folder };
		group.count += 1;
		groups.set(key, group);
	}
	return [...groups.values()];
});
function removeAttachmentGroup(key: string) {
	attachments.value = attachments.value.filter(
		(file) =>
			(file.webkitRelativePath
				? `folder:${file.webkitRelativePath.split("/")[0]}`
				: `file:${file.name}`) !== key,
	);
}
const problemDocument = ref<File | null>(null);
const problemText = ref("");
const executionBackend = ref<ExecutionBackend>("python");
const target = ref("all");
const scrollArea = ref<HTMLElement | null>(null);
const following = ref(true);
const visibleCount = ref(120);
const filter = ref("all");
let stream: EventSource | null = null;
let disposed = false;
let pendingRequest: {
	id: string;
	content: string;
	action?: TeamAction;
	checkpointId?: string;
	planId?: string;
	paperContext?: PaperContext;
	timing?: Adjustment;
} | null = null;
const statuses: Record<string, string> = {
	chat: "对话中",
	idle: "尚未开始",
	preparing: "准备中",
	pending: "待执行",
	running: "执行中",
	completed: "已完成",
	awaiting_approval: "待验收",
	failed: "失败",
	warning: "部分完成，需核验",
	skipped: "已跳过，未验证",
	stopped: "已停止",
	cancelled: "已取消",
	interrupted: "已中断",
	ready: "可开始",
	needs_info: "待补充",
	blocked: "等待建模成果",
};
const projects = computed(() =>
	history.value.filter(
		(item) =>
			item.archived === showArchived.value &&
			item.title.toLowerCase().includes(search.value.toLowerCase()),
	),
);
const filteredEvents = computed(() =>
	events.value.filter(
		(event) =>
			event.kind !== "internal" &&
			event.event_key !== "archive-imported" &&
			(filter.value === "all" || event.role === filter.value),
	),
);
// Page conversation groups, so heartbeats cannot evict their own milestones.
const visibleEvents = filteredEvents;
const timelineItems = computed(() => {
	const items: { id: number | string; event?: TeamEvent; preflight?: boolean; activity: TeamEvent[] }[] = [];
	const plan = state.value?.preflight;
	const anchor = events.value.find(event => event.kind === "preflight" && event.data.id === plan?.id);
	if (plan && (filter.value === "all" || filter.value === "coordinator") && (!anchor || !visibleEvents.value.some(event => event.seq === anchor.seq))) {
		items.push({ id: `preflight:${plan.id}`, preflight: true, activity: [] });
	}
	for (const event of visibleEvents.value) {
		if (plan && event.seq === anchor?.seq) {
			items.push({ id: event.seq, preflight: true, activity: [] });
			continue;
		}
		if (
			["chat", "reply", "error", "execution_summary", "review"].includes(
				event.kind,
			)
		)
			items.push({ id: event.seq, event, activity: [] });
		else {
			let last = items[items.length - 1];
			if (!last || last.event || last.preflight) {
				last = { id: event.seq, activity: [] };
				items.push(last);
			}
			last.activity.push(event);
		}
	}
	return items;
});
const activeStep = computed(() =>
	state.value?.steps.find((step) => step.status === "running"),
);
const visibleTimelineItems = computed(() => timelineItems.value.slice(-visibleCount.value));
const latestActivityId = computed(() => [...timelineItems.value].reverse().find(item => item.activity.length)?.id);
const canSend = computed(
	() =>
		!sending.value &&
		(!!draft.value.trim() ||
			(!props.task_id && (!!problemText.value || !!attachments.value.length))),
);
const conversationPending = computed(() =>
	state.value?.commands?.some((command) => command.status === "running"),
);

function statusLabel(status: string) {
	return statuses[status] || status;
}
function roleStatus(role: string) {
	if (role === "coordinator" && conversationPending.value) return "running";
	const steps = state.value?.steps.filter((step) => step.role === role) ?? [];
	return (
		steps.find((step) =>
			[
				"running",
				"awaiting_approval",
				"failed",
				"warning",
				"interrupted",
				"stopped",
				"cancelled",
				"blocked",
			].includes(step.status),
		)?.status ||
		(steps.length && steps.every((step) => step.status === "completed")
			? "completed"
			: "pending")
	);
}
function formatTime(time: string) {
	return new Date(time).toLocaleTimeString("zh-CN", {
		hour: "2-digit",
		minute: "2-digit",
	});
}
function eventLink(event: TeamEvent) {
	const link = event.data.link;
	return typeof link === "string" &&
		props.task_id &&
		link === `/writing/${props.task_id}`
		? link
		: null;
}
function trackScroll() {
	const el = scrollArea.value;
	if (el)
		following.value = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
}
async function scrollToLatest() {
	await nextTick();
	const el = scrollArea.value;
	if (el) el.scrollTop = el.scrollHeight;
	following.value = true;
}
async function importAttachments(files: File[], documentText = "") {
	if (!files.length) return false;
	error.value = "";
	if (props.task_id) {
		try {
			sending.value = true;
			uploadProgress.value = 0;
			await uploadProjectAttachments(
				props.task_id,
				files,
				documentText,
				(percent) => {
					uploadProgress.value = percent;
				},
			);
			attachmentNotice.value = `已导入 ${files.length} 个文件，可在“文件与结果”查看。`;
			await refreshState();
		} catch (cause) {
			error.value = explainModelingSubmissionFailure(cause);
			return false;
		} finally {
			sending.value = false;
			uploadProgress.value = null;
		}
	} else {
		const existing = new Set(
			attachments.value.map((file) => file.webkitRelativePath || file.name),
		);
		for (const file of files) {
			const path = file.webkitRelativePath || file.name;
			if (!existing.has(path)) {
				attachments.value.push(file);
				existing.add(path);
			}
		}
	}
	return true;
}
async function addAttachments(event: Event) {
	const input = event.target as HTMLInputElement;
	const selected = Array.from(input.files || []);
	input.value = "";
	attachmentNotice.value = "";
	const files = selected.filter(
		(file) =>
			!file.webkitRelativePath ||
			!file.webkitRelativePath
				.split("/")
				.some(
					(part) =>
						part.startsWith(".") || /^(thumbs\.db|desktop\.ini)$/i.test(part),
				),
	);
	const skipped = selected.length - files.length;
	await importAttachments(files);
	if (skipped)
		attachmentNotice.value += ` 已跳过 ${skipped} 个隐藏或系统文件。`;
}
async function acceptProblemDocument(payload: { file: File; text: string }) {
	if (props.task_id) {
		if (await importAttachments([payload.file], payload.text))
			uploadsOpen.value = false;
	} else {
		problemDocument.value = payload.file;
		problemText.value = payload.text;
		uploadsOpen.value = false;
	}
}
async function loadHistory() {
	try {
		const response = await getProjects();
		if (!disposed) history.value = response.data;
	} catch {
		if (!disposed) historyError.value = "项目列表读取失败，请刷新重试。";
	}
}
async function refreshState() {
	if (!props.task_id) return;
	const response = await getTeamState(props.task_id);
	if (!disposed) state.value = response.data;
}
async function send(
	content = draft.value,
	action?: TeamAction,
	timing?: Adjustment,
) {
	if (
		sending.value ||
		(!content.trim() && !problemText.value && !attachments.value.length)
	)
		return;
	adjustmentOpen.value = false;
	sending.value = true;
	error.value = "";
	try {
		if (!props.task_id) {
			const response = await prepareProject(
				{
					ques_all:
						problemText.value ||
						content ||
						"请检查我上传的附件，先和我确认任务目标。",
					user_requirements: problemText.value ? content : "",
					execution_backend: executionBackend.value,
					competition_id: competitionId.value,
					competition_year: String(competitionYear.value),
					paper_language: paperLanguage.value,
					competition_requirements: competitionRequirements.value,
				},
				[
					...attachments.value,
					...(problemDocument.value ? [problemDocument.value] : []),
				],
			);
			sessionStorage.removeItem("team-draft:home");
			await router.push(`/project/${response.data.task_id}`);
			return;
		}
		const message =
			target.value === "all" || action
				? content
				: `@${labels[target.value]} ${content}`;
		if (
			!pendingRequest ||
			pendingRequest.content !== message ||
			pendingRequest.action !== action ||
			pendingRequest.timing !== timing ||
			pendingRequest.checkpointId !==
				state.value?.pending_approval?.checkpoint_id ||
			pendingRequest.planId !== state.value?.preflight?.id
		)
			pendingRequest = {
				id: crypto.randomUUID(),
				content: message,
				action,
				timing,
				checkpointId: state.value?.pending_approval?.checkpoint_id,
				planId: state.value?.preflight?.id,
				paperContext:
					action === "edit_paper"
						? await paperEditor.value?.paperContext()
						: undefined,
			};
		await sendTeamMessage(props.task_id, {
			request_id: pendingRequest.id,
			content: message,
			action,
			timing: pendingRequest.timing,
			conversation_only: !action && !timing && state.value?.status === "running",
			role: target.value,
			checkpoint_id: state.value?.pending_approval?.checkpoint_id,
			plan_id: pendingRequest.planId,
			paper_context: pendingRequest.paperContext,
		});
		pendingRequest = null;
		if (content === draft.value) draft.value = "";
		await scrollToLatest();
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
	} finally {
		sending.value = false;
	}
}
function setDraft(value: string) {
	draft.value = value;
	void nextTick(() => composerInput.value?.focus());
}
function handleKey(event: KeyboardEvent) {
	if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
		event.preventDefault();
		if (canSend.value)
			void send(
				draft.value,
				view.value === "paper" && editPaper.value ? "edit_paper" : undefined,
			);
	}
}

watch(draft, (value) =>
	sessionStorage.setItem(`team-draft:${props.task_id || "home"}`, value),
);
watch(draft, async () => {
	await nextTick();
	const input = composerInput.value;
	if (input) {
		input.style.height = "auto";
		input.style.height = `${Math.min(160, input.scrollHeight)}px`;
	}
});
watch(
	() => events.value.length,
	() => {
		if (following.value) void scrollToLatest();
	},
);
onMounted(async () => {
	draft.value =
		sessionStorage.getItem(`team-draft:${props.task_id || "home"}`) || "";
	void loadHistory();
	if (!props.task_id) {
		try {
			competitions.value = (await getCompetitions()).data;
		} catch {
			error.value = "赛事配置读取失败，请刷新重试。";
		}
	}
	if (!props.task_id) return;
	try {
		await refreshState();
		void refreshProposals().catch(() => {});
		if (disposed) return;
		stream = new EventSource(teamStreamUrl(props.task_id));
		stream.addEventListener("deleted", () => {
			stream?.close();
			if (!disposed) void router.push("/home");
		});
		stream.onopen = () => {
			connection.value = "实时同步";
		};
		stream.onerror = () => {
			connection.value = "连接中断 · 自动重连";
		};
		stream.onmessage = (message) => {
			if (disposed) return;
			try {
				const data = JSON.parse(message.data) as {
					events: TeamEvent[];
					state: TeamState;
				};
				events.value = mergeTeamEvents(events.value, data.events);
				state.value = data.state;
				const entry = history.value.find(
					(item) => item.task_id === props.task_id,
				);
				if (entry) {
					entry.title = data.state.title;
					entry.status = data.state.status;
				}
				if (
					data.events.some((event) =>
						["proposal", "review"].includes(event.kind),
					)
				)
					void refreshProposals().catch(() => {});
			} catch {
				connection.value = "同步数据异常，请刷新";
			}
		};
	} catch (cause) {
		error.value = explainModelingSubmissionFailure(cause);
		connection.value = "未连接";
	}
});
onBeforeUnmount(() => {
	disposed = true;
	stream?.close();
});
</script>

<template>
<div class="team-app" :class="{ 'sidebar-open': sidebarOpen, 'sidebar-collapsed': sidebarCollapsed }" @keydown.esc="optionsOpen = false; adjustmentOpen = false; attachmentMenu = false; projectMenu = ''; sidebarOpen = false">
 <aside class="project-rail" aria-label="项目导航" :aria-hidden="!sidebarVisible" :inert="!sidebarVisible || undefined">
  <RouterLink to="/home" class="brand"><img src="@/assets/remit-icon.png" alt="Remit Logo" /><strong>Remit</strong></RouterLink>
  <RouterLink class="new-chat" to="/home" @click="sidebarOpen = false"><Plus :size="17" />新建项目</RouterLink>
  <input v-model="search" aria-label="搜索项目" class="project-search" placeholder="搜索项目" />
  <div class="rail-caption"><span>{{ showArchived ? '已归档' : '项目' }}</span><button @click="showArchived = !showArchived">{{ showArchived ? '返回项目' : '已归档' }}</button></div>
  <nav class="project-list">
   <div v-for="project in projects" :key="project.task_id" class="project-row" :class="{ selected: project.task_id === task_id }">
    <RouterLink :to="'/project/' + project.task_id" @click="sidebarOpen = false"><MessageSquare :size="15" /><span>{{ project.title }}</span></RouterLink>
    <button :aria-label="'管理项目 ' + project.title" class="project-more" @click="projectMenu = projectMenu === project.task_id ? '' : project.task_id">···</button>
    <div v-if="projectMenu === project.task_id" class="project-menu"><button @click="renameId = project.task_id; renameText = project.title; projectMenu = ''">重命名</button><button @click="manageProject(project, !project.archived)">{{ project.archived ? '恢复项目' : '归档项目' }}</button><button v-if="project.archived" class="danger-text" @click="requestDelete(project)">删除项目</button></div>
   </div>
   <p v-if="!projects.length" class="muted rail-empty">{{ historyError || (search ? '没有匹配的项目' : '项目会保存在这里') }}</p>
  </nav>
  <button class="rail-link" @click="settingsOpen = true"><Settings2 :size="17" />设置</button>
 </aside>
 <button v-if="sidebarOpen" class="rail-scrim" aria-label="关闭项目导航" @click="sidebarOpen = false" />
 <main class="workspace">
  <header class="workspace-header">
   <button class="icon-button" aria-label="切换项目导航" :aria-expanded="narrowScreen ? sidebarOpen : !sidebarCollapsed" :title="(narrowScreen ? sidebarOpen : !sidebarCollapsed) ? '折叠侧栏' : '展开侧栏'" @click="toggleSidebar"><PanelLeft :size="19" /></button>
   <div class="header-title"><span>{{ task_id ? state?.title || '加载项目…' : '新建项目' }}</span><small v-if="state && !['chat','idle'].includes(state.status)">{{ statusLabel(state.status) }}</small></div>
  <nav v-if="task_id" class="workspace-tabs" aria-label="项目视图"><button v-for="tab in [{id:'chat',label:'对话'},{id:'files',label:'文件与结果'},{id:'paper',label:'论文'}]" :key="tab.id" :aria-current="view === tab.id ? 'page' : undefined" @click="changeView(tab.id)">{{ tab.label }}</button></nav>
   <div class="header-actions"><span v-if="task_id && connection !== '实时同步'" class="connection">{{ connection }}</span><button v-if="task_id && view !== 'chat'" class="icon-button" aria-label="切换项目对话" :aria-pressed="chatOpen" @click="chatOpen = !chatOpen; boardOpen = false"><MessageSquare :size="18" /></button><button v-if="task_id" class="icon-button" :aria-expanded="boardOpen" aria-label="切换共享状态表" @click="boardOpen = !boardOpen; chatOpen = false"><ListChecks :size="18" /></button><button v-if="task_id" class="icon-button" aria-label="对话显示选项" :aria-expanded="optionsOpen" @click="optionsOpen = !optionsOpen"><MoreHorizontal :size="18" /></button></div>
  </header>

  <div v-if="optionsOpen" ref="displayOptions" class="display-options"><div class="timeline-filters"><select v-model="filter" aria-label="筛选角色"><option value="all">全部角色</option><option value="coordinator">{{ labels.coordinator }}</option><option value="modeler">{{ labels.modeler }}</option><option value="coder">{{ labels.coder }}</option><option value="writer">{{ labels.writer }}</option></select><label><input v-model="showDetails" type="checkbox" />展开执行明细</label></div></div>
  <div v-if="state?.archived" class="archive-banner">此项目已归档。请在左侧项目菜单中恢复后继续。</div>
  <div class="workspace-content">
   <section v-show="view === 'paper'" class="paper-host"><PaperEditorView v-if="task_id && paperOpened" ref="paperEditor" :task_id="task_id" embedded /></section>
   <ProjectFiles v-if="task_id && view === 'files'" :task_id="task_id" :sequence="state?.sequence || 0" />
   <section v-show="view === 'chat' || chatOpen || !task_id" class="conversation" :class="{copilot:view !== 'chat','new-project':!task_id}">
    <header v-if="view !== 'chat'" class="copilot-heading"><strong>项目对话</strong><button class="icon-button" aria-label="关闭项目对话" @click="chatOpen = false"><X :size="16" /></button></header>
    <RemitWelcome v-if="!task_id" @prompt="setDraft" />
    <div v-else ref="scrollArea" class="conversation-scroll" @scroll="trackScroll">
     <section class="timeline" aria-label="团队对话与执行记录">

      <button v-if="timelineItems.length > visibleCount" class="text-link" @click="visibleCount += 150">查看更早的记录</button>
      <p v-if="!events.length" class="muted">正在读取对话…</p>
      <template v-for="item in visibleTimelineItems" :key="item.id">
      <section v-if="item.preflight && state?.preflight" class="review-card" aria-label="赛题预读计划"><h2>赛题与执行计划</h2><p>{{ state.preflight.understanding }}</p><div v-for="file in state.preflight.attachments" :key="file.file" class="attachment-check"><Paperclip :size="13" /><span>{{ file.file }}</span><small>{{ file.status === 'parsed' ? '已解析' : '保留原件 · 执行时读取' }}</small></div><ol><li v-for="step in state.preflight.steps" :key="step">{{ step }}</li></ol><template v-if="state.preflight.questions.length"><h3>开始前需要补充</h3><ul><li v-for="question in state.preflight.questions" :key="question">{{ question }}</li></ul><p class="muted">在下方回复，协调手会更新计划。</p></template><button v-else class="primary-button" :disabled="sending || conversationPending || state.archived" @click="send('确认当前计划，开始建模','start')">确认计划，开始建模</button></section>
       <article v-else-if="item.event" class="event" :class="{ 'user-event':item.event.role === 'user','event-error':item.event.kind === 'error' }">
        <header v-if="item.event.role !== 'user'" class="role-heading"><RoleAvatar :role="item.event.role" /><span>{{ labels[item.event.role] || 'Remit' }}</span></header>
        <UserMessage v-if="item.event.role === 'user'" :content="item.event.content" />
        <div v-else class="event-content markdown-body" v-html="renderMarkdown(item.event.content)" />
        <button v-if="eventLink(item.event)" class="text-link" @click="changeView('paper')">打开论文 →</button>
        <footer class="message-tools"><span v-if="item.event.role === 'user'">你</span><time>{{ formatTime(item.event.at) }}</time><button v-if="item.event.role !== 'user'" class="icon-button" :aria-label="copied === item.event.seq ? '已复制回复' : '复制回复'" @click="copyReply(item.event)"><Check v-if="copied === item.event.seq" :size="14" /><Copy v-else :size="14" /></button></footer>
       </article>
       <ActivitySummary v-else :events="item.activity" :expanded="showDetails" :state="item.id === latestActivityId ? state : undefined" />
      </template>
      <div v-if="conversationPending" class="thinking"><LoaderCircle :size="15" class="spin" />{{ activeStep?.label || '正在思考' }}</div>
      <HumanApprovalCard v-if="state?.pending_approval" :approval="state.pending_approval" :deciding="sending" @approve="send('批准当前步骤','approve')" @revise="setDraft('请退回当前步骤重做，修改要求：')" @explain="send(approvalExplanationRequest)" @veto="feedback => setDraft('请退回重做：' + feedback)" />
      <section v-for="proposal in proposals" :key="proposal.id" class="review-card" aria-label="论文修改建议"><header><strong>{{ proposal.name }}</strong><span>{{ proposal.status === 'pending' ? '待审阅' : proposal.status === 'accepted' ? '已接受' : '已拒绝' }}</span></header><p>{{ proposal.summary }}</p><details :open="proposal.status === 'pending'"><summary>源码差异</summary><pre class="source-diff"><span v-for="(line,index) in proposal.diff.split('\n')" :key="index" :class="{added:line.startsWith('+'),removed:line.startsWith('-')}">{{ line }}{{ '\n' }}</span></pre></details><div v-if="proposal.status === 'pending'" class="review-actions"><button :disabled="!!deciding" @click="decideProposal(proposal,false)">拒绝</button><button class="primary-button" :disabled="!!deciding" @click="decideProposal(proposal,true)">{{ deciding === proposal.id ? '处理中…' : '接受并编译' }}</button></div></section>
     </section>
    </div>
    <div class="composer-area">
     <div v-if="state?.status === 'failed'" class="recovery-notice" role="status"><span>执行已暂停，文件和进度已保留。</span><button :disabled="sending || conversationPending || state.archived" @click="send('重试当前失败步骤','resume')">重试当前步骤</button></div>
     <button v-if="!following" class="latest-button" @click="scrollToLatest">回到最新 ↓</button>
     <div v-if="uploadsOpen" class="intake-panel"><header><strong>赛题文档</strong><button class="icon-button" aria-label="收起赛题文档" @click="uploadsOpen = false"><X :size="16" /></button></header><ProblemPdfDropzone @parsed="acceptProblemDocument" @cleared="() => { problemDocument = null; problemText = ''; }" /></div>
     <div v-if="!task_id" class="attachment-list"><span v-if="problemDocument"><FileText :size="13" />{{ problemDocument.name }}<button aria-label="移除赛题文档" @click="problemDocument = null; problemText = ''"><X :size="12" /></button></span><span v-for="group in attachmentGroups" :key="group.key"><FolderOpen v-if="group.folder" :size="13" /><Paperclip v-else :size="13" />{{ group.label }}<small v-if="group.folder">{{ group.count }} 个文件</small><button :aria-label="'移除 ' + group.label" @click="removeAttachmentGroup(group.key)"><X :size="12" /></button></span></div>
     <p v-if="uploadProgress !== null" role="status" class="attachment-notice">{{ uploadProgress < 100 ? `正在上传 ${uploadProgress}%` : '正在保存附件…' }}</p><p v-else-if="attachmentNotice" role="status" class="attachment-notice">{{ attachmentNotice }}</p>
     <section v-if="!task_id && contestOptionsOpen" class="contest-options" aria-label="赛事设置"><header><strong>{{ selectedCompetition?.name }}</strong><button class="icon-button" aria-label="关闭赛事设置" @click="contestOptionsOpen = false"><X :size="15" /></button></header><div class="contest-fields"><label>年份 <input v-model.number="competitionYear" aria-label="赛事年份" type="number" min="2000" max="2100" /></label><label>论文语言 <select v-model="paperLanguage" aria-label="论文语言"><option value="">赛事默认</option><option value="zh">中文</option><option value="en">英文</option></select></label></div><textarea v-model="competitionRequirements" aria-label="补充赛事要求" placeholder="补充当届规则、组别、题号、页数或提交要求（可选）" /><small>{{ selectedCompetition?.event_note || (selectedCompetition?.rules_status === 'format_verified' && competitionYear === selectedCompetition.year ? '已核对所列年份的主要版式要求，赛区与提交要求仍需复核' : '已加载建模技能，具体版式请结合当届规则核对') }}</small><a v-for="source in selectedCompetition?.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener">查看赛事资料 ↗</a></section>
     <div v-if="error" role="alert" class="send-error">{{ error }}</div>
     <div v-if="adjustmentOpen" class="adjustment-menu" role="dialog" aria-label="选择调整时机"><header><strong>何时应用这条修改要求？</strong><button class="icon-button" aria-label="关闭调整选项" @click="adjustmentOpen = false"><X :size="15" /></button></header><button @click="send(draft, undefined, 'immediate')"><strong>立即调整</strong><small>停止当前步骤，按新要求继续</small></button><button @click="send(draft, undefined, 'after_step')"><strong>当前步骤完成后调整</strong><small>保留当前执行，将要求加入后续步骤</small></button></div>
     <div class="composer"><textarea ref="composerInput" v-model="draft" rows="1" :aria-label="task_id ? '给团队发送指令' : '描述建模问题'" :placeholder="view === 'paper' && editPaper ? '描述修改要求，可先在源码中选中一段…' : task_id ? '继续对话，或提出修改…' : problemText ? '补充要求（可选）' : '把题目、想法，或卡住的地方告诉 Remit…'" @keydown="handleKey" />
      <div class="composer-toolbar"><div class="composer-options">
       <div class="attachment-control"><button class="icon-button" aria-label="添加赛题或数据" :disabled="sending || state?.archived" :aria-expanded="attachmentMenu" @click="attachmentMenu = !attachmentMenu"><Plus :size="19" /></button><div v-if="attachmentMenu" class="attachment-menu"><button @click="uploadsOpen = true; attachmentMenu = false"><FileText :size="15" />赛题文档 <small>PDF / Word</small></button><button @click="fileInput?.click(); attachmentMenu = false"><Paperclip :size="15" />数据附件 <small>不限格式 · 多选</small></button><button @click="folderInput?.click(); attachmentMenu = false"><FolderOpen :size="15" />数据文件夹 <small>包含子文件夹</small></button></div></div>
       <template v-if="!task_id"><select v-model="executionBackend" aria-label="计算环境"><option value="python">Python</option><option value="matlab">MATLAB</option></select><select v-model="competitionId" aria-label="选择数学建模竞赛"><option v-for="contest in competitions" :key="contest.id" :value="contest.id">{{ contest.name }}</option></select><button class="icon-button" aria-label="赛事设置" @click="contestOptionsOpen = !contestOptionsOpen"><Settings2 :size="15" /></button></template>
       <select v-if="task_id && view !== 'paper'" v-model="target" aria-label="指派角色"><option value="all">{{ labels.coordinator }}</option><option value="modeler">@ {{ labels.modeler }}</option><option value="coder">@ {{ labels.coder }}</option><option value="writer">@ {{ labels.writer }}</option></select><label v-if="task_id && view === 'paper'" class="edit-mode"><input v-model="editPaper" type="checkbox" />修改源码</label>
      </div><div class="send-actions"><button v-if="state?.status === 'running' && view !== 'paper'" class="text-link" :disabled="!draft.trim() || sending || state?.archived" @click="adjustmentOpen = !adjustmentOpen">调整任务</button><button v-if="state?.status === 'running'" class="icon-button" aria-label="停止建模" @click="send('停止建模','stop')"><Square :size="15" /></button><button class="send-button" :disabled="!canSend || state?.archived" :aria-label="'发送'" @click="send(draft, view === 'paper' && editPaper ? 'edit_paper' : undefined)"><LoaderCircle v-if="sending" :size="17" class="spin" /><ArrowUp v-else :size="19" /></button></div></div>
     </div>
     <p class="composer-hint">{{ !task_id ? '普通消息直接对话；建模任务先确认计划，再开始执行' : view === 'paper' && editPaper ? '修改建议经你接受后才写入源码' : state?.status === 'running' ? 'Enter 对话 · 调整执行请点“调整任务”' : 'Enter 发送 · Shift + Enter 换行' }}</p>
    </div>
   </section>
   <aside v-if="task_id && boardOpen" class="shared-board" aria-label="共享全局状态表"><header><h2>项目进度</h2><button class="icon-button" aria-label="关闭状态表" @click="boardOpen = false"><X :size="17" /></button></header><div class="role-grid"><div v-for="role in ['coordinator','modeler','coder','writer']" :key="role"><span class="role-name"><RoleAvatar :role="role" compact />{{ labels[role] }}</span><small>{{ statusLabel(roleStatus(role)) }}</small></div></div><ol class="step-list"><li v-for="step in state?.steps" :key="step.id"><Check v-if="step.status === 'completed'" :size="14" /><span v-else class="step-dot" /><div>{{ step.label }}<small>{{ statusLabel(step.status) }}</small></div></li></ol><button v-if="state?.status === 'completed'" class="primary-button" @click="send('用已验收成果生成论文初稿','write')">开始论文写作</button><button v-if="['stopped','failed'].includes(state?.status || '')" class="primary-button" @click="send('继续建模','resume')">继续建模</button><div v-for="item in state?.directives" :key="item.id" class="directive"><p>{{ item.content }}</p><small>{{ item.seen.map(role => labels[role]).join('、') || '等待角色读取' }}</small></div></aside>
  </div>
 </main>
 <input ref="fileInput" type="file" multiple hidden aria-label="选择数据附件" @change="addAttachments" /><input ref="folderInput" type="file" webkitdirectory multiple hidden aria-label="选择数据文件夹" @change="addAttachments" /><ApiDialog v-model:open="settingsOpen" />
 <AlertDialogRoot :open="!!deleteTarget" @update:open="closeDelete">
  <AlertDialogOverlay class="delete-overlay" />
  <AlertDialogContent class="delete-dialog" @escape-key-down="deleting && $event.preventDefault()">
   <AlertDialogTitle class="delete-title">删除“{{ deleteTarget?.title }}”？</AlertDialogTitle>
   <AlertDialogDescription class="delete-description">这将永久删除此项目的全部对话、上传附件、代码、计算结果和论文文件，无法恢复。</AlertDialogDescription>
   <p v-if="deleteError" role="alert" class="danger-text">{{ deleteError }}</p>
   <footer><AlertDialogCancel :disabled="deleting">取消</AlertDialogCancel><button class="delete-confirm" :disabled="deleting" @click="confirmDelete">{{ deleting ? '正在删除…' : '永久删除' }}</button></footer>
  </AlertDialogContent>
 </AlertDialogRoot>
 <div v-if="renameId" class="modal-backdrop" @click.self="renameId = ''"><form class="rename-dialog" role="dialog" aria-modal="true" aria-label="重命名项目" @submit.prevent="renameProject"><h2>重命名项目</h2><input v-model="renameText" aria-label="项目名称" maxlength="100" autofocus /><footer><button type="button" @click="renameId = ''">取消</button><button class="primary-button" type="submit" :disabled="!renameText.trim()">保存</button></footer></form></div>
</div>
</template>
<style scoped src="./workspace.css"></style>

<style scoped>
.markdown-body :deep(p) { margin:0 0 12px; }
.markdown-body :deep(p:last-child) { margin-bottom:0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left:24px;margin:12px 0; }
.markdown-body :deep(ul) { list-style:disc; }
.markdown-body :deep(ol) { list-style:decimal; }
.markdown-body :deep(li) { margin:5px 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { font-size:16px;font-weight:600;margin:20px 0 10px; }
.markdown-body :deep(pre) { padding:14px 16px;background:#f7f7f7;border:1px solid #eaeaea;border-radius:8px;overflow:auto;font:12px/1.7 Consolas,monospace;margin:14px 0; }
.markdown-body :deep(code) { font-size:.9em; }
.markdown-body :deep(a) { text-decoration:underline;text-underline-offset:3px; }
.markdown-body :deep(table) { display:block;overflow:auto;border-collapse:collapse;max-width:100%;margin:14px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding:8px 12px;border:1px solid #e5e5e5;text-align:left; }
</style>
