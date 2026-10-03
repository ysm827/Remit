<script setup lang="ts">
import { renderMarkdown } from "@/utils/markdown";
import { computed } from "vue";

const props = defineProps<{ content: string; taskId?: string }>();
// Each mounted message owns its sanitized HTML. Unrelated stream updates and
// draft edits cannot reparse it; content/project changes still run sanitization.
const html = computed(() =>
	renderMarkdown(props.content, {}, { taskId: props.taskId }),
);
</script>

<template>
 <div class="event-content markdown-body" v-html="html" />
</template>
