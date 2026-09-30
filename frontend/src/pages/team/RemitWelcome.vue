<script setup lang="ts">
import RoleAvatar from "./RoleAvatar.vue";
import { teamMembers } from "./roles";
defineEmits<{ prompt: [value: string] }>();
</script>

<template>
 <section class="remit-welcome" aria-label="认识 Remit 数模小队">
  <img class="welcome-logo" src="@/assets/remit-icon.png" alt="Remit" />
  <h1>嗨，我是 Remit！</h1>
  <p class="intro">你的数模小助手。一起读题、建模、计算，把成果写清楚。</p>
  <div class="crew" aria-label="选择一个话题开始">
   <button v-for="member in teamMembers" :key="member.role" type="button" :title="member.description + ' · 点击填入话题'" @click="$emit('prompt', member.prompt)">
    <RoleAvatar :role="member.role" compact /><span>{{ member.name }}<small>{{ member.job }}</small></span>
   </button>
  </div>
 </section>
</template>

<style scoped>
.remit-welcome{width:100%;max-width:760px;padding:0 26px;margin:0 auto 22px;color:var(--ink,#202020)}
.welcome-logo{width:44px;height:44px;object-fit:contain;margin-bottom:18px}
h1{font-size:clamp(25px,3vw,30px);font-weight:600;letter-spacing:-.5px;line-height:1.35}
.intro{margin:10px 0 20px;color:#666;line-height:1.8;font-size:14px}
.crew{display:flex;flex-wrap:wrap;gap:6px 16px}
.crew button{display:flex;align-items:center;gap:7px;text-align:left;padding:6px 4px;border-radius:7px;transition:background .15s;font-size:12px}
.crew button:hover{background:#f3f3f3}.crew button:focus-visible{outline:2px solid #777;outline-offset:3px}.crew small{color:#737373;font-weight:400;margin-left:6px;font-size:11px}
@media(max-width:520px){.remit-welcome{padding:0 18px}.crew{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 10px}.intro{font-size:13px}.welcome-logo{width:38px;height:38px;margin-bottom:14px}}
@media(prefers-reduced-motion:reduce){.crew button{transition:none}}
</style>
