<script setup lang="ts">
import { useResizeObserver } from "@vueuse/core";
import { nextTick, onMounted, ref, useId, watch } from "vue";

const props = defineProps<{ content: string }>();
const text = ref<HTMLElement | null>(null);
const expanded = ref(false);
const collapsible = ref(
	props.content.length > 320 || props.content.split("\n").length > 6,
);
const contentId = useId();
function measure() {
	const element = text.value;
	if (!element) return;
	const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
	if (lineHeight && element.scrollHeight) {
		collapsible.value = element.scrollHeight > lineHeight * 6 + 2;
	}
}
useResizeObserver(text, measure);
onMounted(measure);
watch(
	() => props.content,
	async () => {
		await nextTick();
		measure();
	},
);
</script>

<template>
	<div class="user-message">
		<p ref="text" :id="contentId" class="event-content" :class="{ 'message-collapsed': !expanded }">{{ content }}</p>
		<button
			v-if="collapsible"
			class="message-toggle"
			:aria-expanded="expanded"
			:aria-controls="contentId"
			@click="expanded = !expanded"
		>{{ expanded ? "收起" : "展开全文" }}</button>
	</div>
</template>

<style scoped>
.event-content {
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	font-size: 15px;
	line-height: 1.75;
}
.message-collapsed {
	max-height: 10.5em;
	overflow: hidden;
}
.message-toggle {
	display: block;
	margin: 8px 0 0 auto;
	padding: 3px 0;
	color: #666;
	font-size: 12px;
}
.message-toggle:hover { color: #222; }
.message-toggle:focus-visible {
	outline: 2px solid #666;
	outline-offset: 3px;
	border-radius: 3px;
}
</style>
