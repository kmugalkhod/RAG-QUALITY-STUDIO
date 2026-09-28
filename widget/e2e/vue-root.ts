/* A local Vue shared-root-layout integration fixture. */
import { createApp, defineComponent, h, onMounted, ref } from 'vue';

const SharedLayout = defineComponent({
  setup() {
    const route = ref(location.pathname);
    onMounted(() => {
      const script = document.createElement('script');
      script.async = true;
      script.src = 'http://127.0.0.1:5274/v1.0.0/loader.js';
      script.dataset.rqsDeploymentId = document.body.dataset.deploymentId || '';
      script.dataset.rqsTokenUrl = '/api/rag-widget/token';
      document.body.append(script);
    });
    const go = (path: string) => { history.pushState({}, '', path); route.value = path; };
    return () => h('div', [
      h('header', [h('h1', 'Vue customer layout'), h('nav', [
        h('button', { onClick: () => go('/vue') }, 'Overview'),
        h('button', { onClick: () => go('/vue/help') }, 'Help'),
      ])]),
      h('main', [h('h2', route.value.endsWith('/help') ? 'Help route' : 'Overview route'), h('p', 'The assistant belongs to the shared Vue root layout.')]),
    ]);
  },
});

createApp(SharedLayout).mount('#app');
