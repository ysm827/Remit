import { config } from "@vue/test-utils";

// Business tests exercise the form state/actions in place. Portal placement and
// dismissal are covered independently in floating-panel.test.ts and the browser.
config.global.stubs.FloatingPanel = {
 props: ["open", "title", "id"],
 emits: ["update:open"],
 template: '<section v-if="open" role="dialog" :id="id" :aria-label="title"><slot /><button :aria-label="`关闭${title}`" @click="$emit(\'update:open\', false)">关闭</button></section>',
};
