<script setup lang="ts">
import type { ProjectEntry } from "@/apis/teamApi";
import { ChevronRight, FileText, FolderOpen, MessageSquare, Search } from "lucide-vue-next";
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

const props = defineProps<{
 view: "chat" | "files" | "paper";
 projects: ProjectEntry[];
 loading: boolean;
 error: string;
}>();
defineEmits<{ retry: [] }>();
const search = ref("");
const archived = ref(false);
const labels = { chat: "对话", files: "文件与结果", paper: "论文" };
const icons = { chat: MessageSquare, files: FolderOpen, paper: FileText };
const descriptions = {
 chat: "按项目继续对话，回看讨论与执行记录。",
 files: "按项目查看附件、代码、图表与计算结果。",
 paper: "按项目打开论文，查看源码与 PDF。",
};
const filtered = computed(() => props.projects.filter(project =>
 project.archived === archived.value && project.title.toLowerCase().includes(search.value.trim().toLowerCase()),
));
function projectUrl(id: string) {
 return `/project/${encodeURIComponent(id)}${props.view === "chat" ? "" : `?view=${props.view}`}`;
}
function dateLabel(value: string) {
 const date = new Date(value);
 return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}
</script>

<template>
 <section class="workspace-library" :aria-label="`${labels[view]}项目目录`" :aria-busy="loading">
  <div class="library-inner">
   <header class="library-heading"><h1>{{ labels[view] }}</h1><p>{{ descriptions[view] }}</p></header>
   <div class="library-toolbar">
    <label class="library-search"><Search :size="16" aria-hidden="true" /><input v-model="search" aria-label="在目录中搜索项目" placeholder="搜索项目" /></label>
    <button :aria-pressed="archived" @click="archived = !archived">{{ archived ? '已归档' : '未归档' }}</button>
   </div>
   <p v-if="loading" class="library-empty" role="status">正在读取项目…</p>
   <div v-else-if="error" class="library-empty" role="alert"><p>{{ error }}</p><button class="text-link" @click="$emit('retry')">重试</button></div>
   <template v-else-if="filtered.length">
    <div class="library-list-heading"><span>项目</span><span>最近更新</span></div>
    <ul class="library-list">
     <li v-for="project in filtered" :key="project.task_id">
      <RouterLink :to="projectUrl(project.task_id)"><component :is="icons[view]" :size="18" aria-hidden="true" /><span>{{ project.title }}</span><time :datetime="project.updated_at">{{ dateLabel(project.updated_at) }}</time><ChevronRight :size="15" aria-hidden="true" /></RouterLink>
     </li>
    </ul>
   </template>
   <div v-else class="library-empty"><component :is="icons[view]" :size="27" aria-hidden="true" /><p>{{ search ? '没有匹配的项目' : archived ? '没有归档项目' : '还没有项目' }}</p><span v-if="search">试试其他项目名称。</span><template v-else-if="!archived"><span>创建项目后，可以在这里找到{{ labels[view] }}。</span><RouterLink to="/home" class="library-create">新建项目</RouterLink></template></div>
  </div>
 </section>
</template>

<style scoped>
.workspace-library{flex:1;min-width:0;overflow:auto;padding:48px 40px}
.library-inner{max-width:880px;margin:0 auto}
.library-heading h1{font-size:25px;line-height:1.4;font-weight:600;letter-spacing:-.5px;margin:0 0 8px}
.library-heading p{color:var(--muted);font-size:13px;margin:0}
.library-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:30px 0 22px}
.library-search{display:flex;align-items:center;gap:9px;color:var(--muted);width:300px;max-width:100%;padding:8px 11px;background:#f7f7f7;border-radius:8px}
.library-search input{background:transparent;border:0;outline:none;min-width:0;width:100%;font-size:13px}
.library-search:focus-within{outline:2px solid #777;outline-offset:2px}
.library-toolbar button{flex-shrink:0;font-size:12px;color:var(--muted);padding:6px 10px;border:1px solid var(--line);border-radius:6px}
.library-toolbar button:hover,.library-toolbar button[aria-pressed=true]{background:#f3f3f3;color:var(--ink)}
.library-list-heading{display:flex;justify-content:space-between;padding:0 36px 10px 12px;color:var(--muted);font-size:11px;border-bottom:1px solid var(--line)}
.library-list{list-style:none;padding:0;margin:0}
.library-list li{border-bottom:1px solid #f0f0f0}
.library-list a{display:flex;align-items:center;gap:13px;padding:18px 12px;border-radius:7px}
.library-list a:hover{background:#f7f7f7}
.library-list svg{flex-shrink:0;color:#777}
.library-list a>span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.library-list time{color:var(--muted);font-size:12px;white-space:nowrap}
.library-empty{display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;padding:62px 16px;color:var(--muted);font-size:13px}
.library-empty p{color:var(--ink);margin:6px 0 0;font-size:14px}
.library-empty .library-create{margin-top:12px;color:var(--ink);border:1px solid var(--line);padding:7px 16px;border-radius:7px}
.library-create:hover{background:#f5f5f5}
@media(max-width:600px){.workspace-library{padding:30px 20px}.library-heading h1{font-size:22px}.library-list a{gap:9px;padding:16px 4px}.library-toolbar{gap:10px}}
</style>
