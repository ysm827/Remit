<script setup lang="ts">
import Toaster from "@/components/ui/toast/Toaster.vue";
import { RouterView } from "vue-router";
</script>

<template>
  <Toaster />
  <RouterView v-slot="{ Component, route }">
    <component
      :is="Component"
      :key="String(route.params.task_id ?? route.params.projectId ?? route.path)"
    />
  </RouterView>
</template>
