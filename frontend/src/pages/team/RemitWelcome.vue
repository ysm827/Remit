<template>
 <section class="remit-welcome" aria-label="新建建模项目">
  <img class="welcome-mark" src="@/assets/remit-icon.png" alt="" />
  <h1>今天想解决什么问题？</h1>
  <p class="intro">读题、建模、计算，到一份完整的论文。</p>
 </section>
</template>

<style scoped>
.remit-welcome{width:100%;max-width:880px;padding:0 24px;margin:0 auto clamp(32px,6vh,64px);text-align:center;color:var(--ink)}
.welcome-mark{width:42px;height:42px;object-fit:contain;margin:0 auto 24px;border-radius:8px}
h1{font-size:clamp(26px,2.6vw,36px);font-weight:500;letter-spacing:-.8px;line-height:1.45}
.intro{margin-top:12px;color:var(--muted);line-height:1.75;font-size:14px}
@media(max-width:600px){.remit-welcome{padding:0 20px;margin-bottom:32px}.welcome-mark{width:34px;height:34px;margin-bottom:20px}.intro{font-size:13px}}
</style>
