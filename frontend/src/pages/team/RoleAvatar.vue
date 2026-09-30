<script setup lang="ts">
import { UserRound, UserRoundCog, UserRoundPen, UserRoundSearch, UsersRound } from "lucide-vue-next";
import { roleLabels } from "./roles";

defineProps<{ role: string; compact?: boolean }>();
const icons = { coordinator: UsersRound, modeler: UserRoundSearch, coder: UserRoundCog, writer: UserRoundPen };
</script>

<template>
 <span class="role-avatar" :class="[role, { compact }]" :data-role="role" role="img" :aria-label="roleLabels[role] || 'Remit'">
  <component :is="icons[role as keyof typeof icons] || UserRound" :size="compact ? 15 : 18" :stroke-width="1.65" aria-hidden="true" />
 </span>
</template>

<style scoped>
.role-avatar{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:28px;height:28px;border-radius:50%;background:#f3f3f3;color:#555}
.role-avatar.coordinator{background:#f0f1f3;color:#536174}.role-avatar.modeler{background:#edf3ef;color:#4e725b}.role-avatar.coder{background:#eef2f8;color:#4f6f99}.role-avatar.writer{background:#f4eff5;color:#84658b}
.role-avatar.compact{width:22px;height:22px}
</style>
