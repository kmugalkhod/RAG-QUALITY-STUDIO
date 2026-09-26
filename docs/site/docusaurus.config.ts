import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'RAG Quality Studio',
  tagline: 'Build a collection. Ask with evidence. Compare saved work.',
  url: process.env.DOCS_SITE_URL || 'http://127.0.0.1:3000',
  baseUrl: '/',
  trailingSlash: true,
  favicon: 'img/favicon.svg',
  onBrokenLinks: 'throw',
  markdown: {hooks: {onBrokenMarkdownLinks: 'throw'}},
  organizationName: 'rag-quality-studio',
  projectName: 'rag-quality-studio',
  i18n: {defaultLocale: 'en', locales: ['en']},
  presets: [[
    'classic',
    {
      docs: {routeBasePath: 'docs', sidebarPath: './sidebars.ts', editUrl: undefined},
      blog: false,
      theme: {customCss: './src/css/custom.css'},
    } satisfies Preset.Options,
  ]],
  themes: [[
    require.resolve('@easyops-cn/docusaurus-search-local'),
    {hashed: true, docsRouteBasePath: '/docs', indexBlog: false, indexPages: false, highlightSearchTermsOnTargetPage: true, ignoreFiles: [/docs\/api\/schema-models\/?$/]},
  ]],
  themeConfig: {
    colorMode: {defaultMode: 'dark', disableSwitch: true, respectPrefersColorScheme: false},
    navbar: {
      title: 'RAG Quality Studio',
      items: [
        {type: 'docSidebar', sidebarId: 'guide', label: 'Guides', position: 'left'},
        {to: '/docs/api/overview', label: 'API', position: 'left'},
        {to: '/docs/reference/limits-faq', label: 'Local tree · 481b4ec+', position: 'right'},
        {href: process.env.DOCS_APP_URL || 'http://127.0.0.1:5273', label: 'Open local app', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      copyright: 'Documentation for the current local application. Verify configured providers before use.',
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
