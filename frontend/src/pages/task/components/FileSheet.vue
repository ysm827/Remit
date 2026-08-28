<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
	SheetTrigger,
} from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast/use-toast";
import { useWorkspaceFiles } from "@/composables/useWorkspaceFiles";
import {
	Archive,
	Download,
	FileText,
	FolderOpen,
	LoaderCircle,
} from "lucide-vue-next";
import { ref } from "vue";
import { useRoute } from "vue-router";

const props = defineProps<{ taskId?: string }>();
const route = useRoute();
const taskId = String(
	props.taskId || route.params.task_id || route.params.projectId || "",
);
const open = ref(false);
const { toast } = useToast();

const notice = (title: string, description: string, destructive = false) =>
	toast({
		title,
		description,
		...(destructive ? { variant: "destructive" as const } : {}),
	});

const {
	files,
	busy,
	isListing,
	isArchiving,
	filename,
	fileSize,
	refresh,
	download,
} = useWorkspaceFiles(taskId, notice);

async function reveal(): Promise<void> {
	if (await refresh()) open.value = true;
}
</script>

<template>
  <Sheet v-model:open="open">
    <SheetTrigger as-child>
      <Button size="icon" aria-label="查看工作区文件" :disabled="isListing" @click="reveal">
        <LoaderCircle v-if="isListing" class="h-4 w-4 animate-spin" />
        <FolderOpen v-else class="h-4 w-4" />
      </Button>
    </SheetTrigger>

    <SheetContent side="right" class="flex w-[420px] flex-col sm:w-[560px]">
      <SheetHeader class="pr-6">
        <div class="flex items-start justify-between gap-4">
          <div>
            <SheetTitle>任务产物</SheetTitle>
            <SheetDescription class="mt-1">
              共 {{ files.length }} 个文件；可单独取用，也可下载完整归档。
            </SheetDescription>
          </div>
          <Button variant="outline" size="sm" :disabled="!files.length || busy !== null"
            @click="download()">
            <LoaderCircle v-if="isArchiving" class="mr-2 h-4 w-4 animate-spin" />
            <Archive v-else class="mr-2 h-4 w-4" />
            打包下载
          </Button>
        </div>
      </SheetHeader>

      <ScrollArea class="mt-6 min-h-0 flex-1 pr-3">
        <div v-if="files.length === 0"
          class="rounded-xl border border-dashed px-6 py-12 text-center text-sm text-muted-foreground">
          当前节点还没有生成可下载文件。
        </div>
        <ul v-else class="space-y-2" aria-label="任务文件列表">
          <li v-for="file in files" :key="filename(file)"
            class="group flex items-center gap-3 rounded-xl border bg-background p-3">
            <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-muted">
              <FileText class="h-4 w-4" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium" :title="filename(file)">{{ filename(file) }}</p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ file.file_type || file.type || "文件" }}<span v-if="fileSize(file)"> · {{ fileSize(file) }}</span>
              </p>
            </div>
            <Button size="icon" variant="ghost" :aria-label="`下载 ${filename(file)}`"
              :disabled="busy !== null" @click="download(file)">
              <LoaderCircle v-if="busy === filename(file)" class="h-4 w-4 animate-spin" />
              <Download v-else class="h-4 w-4" />
            </Button>
          </li>
        </ul>
      </ScrollArea>
    </SheetContent>
  </Sheet>
</template>
