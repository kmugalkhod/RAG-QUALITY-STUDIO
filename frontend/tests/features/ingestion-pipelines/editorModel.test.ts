import {
  defaultIngestionDraft,
  describeCadence,
  describeIngestionNode,
  upgradeIngestionDraft,
} from '../../../src/features/ingestion-pipelines/editorModel';

describe('ingestion editor model', () => {
  test('builds the supported linear draft without losing embedding identity', () => {
    const draft = defaultIngestionDraft(
      {
        provider: 'test',
        model: 'embedding-v1',
        dimensions: 3,
        revision: 'revision-2',
        endpoint_id: 'endpoint-1',
      },
      ['document-1'],
    );

    expect(draft.execution.nodes.map((node) => node.type)).toEqual([
      'source',
      'extract',
      'clean',
      'chunk',
      'embed',
      'publish_index',
    ]);
    expect(draft.execution.schema_version).toBe(2);
    expect(draft.execution.nodes.find((node) => node.type === 'extract')).toMatchObject({
      strategy: 'auto',
      ocr: { mode: 'off', languages: ['eng'] },
      quality_policy: 'default-v1',
      config_version: 'layout-ocr-v1',
    });
    expect(draft.execution.edges).toEqual([
      { source: 'source', target: 'extract' },
      { source: 'extract', target: 'clean' },
      { source: 'clean', target: 'chunk' },
      { source: 'chunk', target: 'embed' },
      { source: 'embed', target: 'publish' },
    ]);
    expect(draft.execution.nodes.find((node) => node.type === 'embed')).toMatchObject({
      provider: 'test',
      model: 'embedding-v1',
      dimensions: 3,
      config_version: 'revision-2',
    });
  });

  test('upgrades a legacy version only in a detached draft', () => {
    const legacy = defaultIngestionDraft(
      {
        provider: 'test',
        model: 'embedding-v1',
        dimensions: 3,
        revision: '1',
        endpoint_id: 'endpoint-1',
      },
      ['document-1'],
    );
    legacy.execution.schema_version = 1;
    const extract = legacy.execution.nodes.find((node) => node.type === 'extract')!;
    if (extract.type === 'extract') {
      extract.strategy = 'media_type_registry';
      extract.config_version = '1';
    }

    const upgraded = upgradeIngestionDraft(legacy);
    expect(legacy.execution.schema_version).toBe(1);
    expect(upgraded.execution.schema_version).toBe(2);
    expect(upgraded.execution.nodes.find((node) => node.type === 'clean')).toMatchObject({
      profile: 'standard-v1',
      config_version: 'deterministic-clean-v1',
    });
  });

  test('keeps concise stage descriptions stable', () => {
    const draft = defaultIngestionDraft(
      {
        provider: 'test',
        model: 'embedding-v1',
        dimensions: 3,
        revision: '1',
        endpoint_id: 'endpoint-1',
      },
      ['document-1'],
    );
    const source = draft.execution.nodes[0];
    const extract = draft.execution.nodes.find((node) => node.type === 'extract')!;
    const chunk = draft.execution.nodes.find((node) => node.type === 'chunk')!;

    expect(describeIngestionNode(source, [])).toBe('1 selected document');
    expect(describeIngestionNode(extract, [])).toBe('Auto · OCR off');
    expect(describeIngestionNode(chunk, [])).toBe('1000 characters · 100 overlap');
  });

  test('describes interval and daily schedules without changing cadence data', () => {
    const base = {
      id: 'schedule-1',
      project_id: 'project-1',
      name: 'Sync',
      pipeline_id: 'pipeline-1',
      pipeline_version_id: 'version-1',
      pipeline_version: 1,
      status: 'enabled' as const,
      next_run_at: null,
      last_run_id: null,
      last_triggered_at: null,
      last_outcome: null,
      last_error: null,
      created_at: '2026-09-23T00:00:00Z',
      updated_at: '2026-09-23T00:00:00Z',
    };

    expect(describeCadence({ ...base, cadence: { kind: 'interval', minutes: 1440 } })).toBe(
      'Every day',
    );
    expect(
      describeCadence({
        ...base,
        cadence: { kind: 'daily', local_time: '09:30', timezone: 'Asia/Kolkata' },
      }),
    ).toBe('Daily at 09:30 Asia/Kolkata');
  });
});
