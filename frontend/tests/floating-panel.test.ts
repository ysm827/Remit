import FloatingPanel from "@/pages/team/FloatingPanel.vue";
import { DOMWrapper, flushPromises, mount } from "@vue/test-utils";
import { defineComponent, ref } from "vue";
import { expect, it } from "vitest";

it("详情挂载在正文外，关闭后保留未保存字段，再开可继续编辑", async () => {
 const host = defineComponent({
  components: { FloatingPanel },
  setup() { return { open: ref(false), draft: ref("") }; },
  template: '<main><button @click="open = true">打开</button><p>原页面</p><FloatingPanel v-model:open="open" title="测试详情"><input v-model="draft" aria-label="未保存意见" /></FloatingPanel></main>',
 });
 const wrapper = mount(host, { attachTo: document.body });
 try {
  await wrapper.get("button").trigger("click");
  await flushPromises();
  const element = document.querySelector('[role="dialog"]');
  if (!element) throw new Error("浮窗未显示");
  const dialog = new DOMWrapper(element);
  expect(dialog.exists()).toBe(true);
  expect(wrapper.element.contains(dialog.element)).toBe(false);
  await dialog.get("input").setValue("保留这段修改");
  await dialog.get('[aria-label="关闭测试详情"]').trigger("click");
  await flushPromises();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  await wrapper.get("button").trigger("click");
  await flushPromises();
  expect((document.querySelector('[aria-label="未保存意见"]') as HTMLInputElement).value).toBe("保留这段修改");
 } finally { wrapper.unmount(); }
});
