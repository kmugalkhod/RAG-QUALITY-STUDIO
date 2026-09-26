import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  guide: [
    {type: 'category', label: 'Start', items: ['start/index', 'start/install', 'start/configure', 'start/first-workflow']},
    {type: 'category', label: 'Concepts', items: ['concepts/workflow', 'concepts/glossary', 'concepts/projects', 'concepts/versions']},
    {type: 'category', label: 'Knowledge Base', items: ['knowledge-base/index', 'knowledge-base/documents', 'knowledge-base/prepare', 'knowledge-base/collections']},
    {type: 'category', label: 'Sources and ingestion', items: [
      'ingestion/sources/index',
      'ingestion/connections',
      'ingestion/sources/website',
      'ingestion/sources/s3',
      'ingestion/sources/notion',
      'ingestion/sources/confluence',
      'ingestion/pipelines',
      'ingestion/extraction',
      'ingestion/cleaning',
      'ingestion/chunking',
      'ingestion/previews',
      'ingestion/runs',
      'ingestion/quality',
      'ingestion/source-history',
    ]},
    {type: 'category', label: 'Answers', items: ['answers/pipelines', 'answers/retrieval', 'answers/playground', 'answers/evidence', 'answers/history']},
    {type: 'category', label: 'Experiments', items: ['experiments/datasets', 'experiments/runs', 'experiments/metrics', 'experiments/compare', 'experiments/interpret']},
    {type: 'category', label: 'API', items: [
      'api/overview', 'api/patterns', 'api/reference', 'api/recipes',
      {type: 'category', label: 'Endpoint contracts', items: [
        'api/reference/health', 'api/reference/projects', 'api/reference/connections',
        'api/reference/documents', 'api/reference/pipelines', 'api/reference/ingestion',
        'api/reference/indexes', 'api/reference/queries', 'api/reference/evaluation',
      ]},
      'api/schema-models',
    ]},
    {type: 'category', label: 'Operate', items: [
      'operate/deploy', 'operate/security', 'operate/backup-restore',
      'operate/operations', 'operate/troubleshooting', 'operate/release',
    ]},
    {type: 'category', label: 'Reference', items: ['reference/limitations', 'reference/limits-faq']},
  ],
};
export default sidebars;
