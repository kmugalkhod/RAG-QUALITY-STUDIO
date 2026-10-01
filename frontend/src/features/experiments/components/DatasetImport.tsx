import { useRef, useState } from 'react';
import { ChevronRight, Download } from 'lucide-react';
import { CARD, InlineError, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { number } from '../format';
import type { Dataset, Preview } from '../model';
import * as api from '../api';
import { Questions } from './Questions';
import { docsHref } from '../../../lib/docs';
import { downloadFile } from '../../../lib/api';
import { cn } from '../../../lib/utils';
import { StageNumber } from './parts';

const CHEVRON = 'transition-transform duration-(--transition-fast) group-open:rotate-90';

type EvaluationOptions = Awaited<ReturnType<typeof api.getEvaluationOptions>>;

export function DatasetImport({
  projectId,
  datasets,
  options,
  selectedDatasetId,
  onDatasetChange,
  onImported,
}: {
  projectId: string;
  datasets: Dataset[];
  options?: EvaluationOptions;
  selectedDatasetId: string;
  onDatasetChange: (datasetId: string) => void;
  onImported: (dataset: Dataset) => void;
}) {
  const request = useRef(0);
  const [file, setFile] = useState<File>();
  const [name, setName] = useState('');
  const [identity, setIdentity] = useState('');
  const [preview, setPreview] = useState<Preview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [importOpen, setImportOpen] = useState(!datasets.length);

  async function loadPreview() {
    if (!file) {
      return;
    }
    const requestId = ++request.current;
    setBusy(true);
    setError('');
    try {
      const result = await api.previewDataset(projectId, file);
      if (requestId === request.current) {
        setPreview(result);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function importDataset() {
    if (!file || !preview || preview.errors.length || !name.trim()) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      onImported(await api.importDataset(projectId, file, name, preview.content_hash, identity));
      setPreview(undefined);
      setFile(undefined);
      setName('');
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const selectedDataset = datasets.find((dataset) => dataset.id === selectedDatasetId);

  return (
    <section
      aria-labelledby="dataset-stage-title"
      className={cn(CARD, 'flex min-w-0 flex-col gap-4 p-4 md:p-6 desktop:col-start-1')}
    >
      <div className="flex items-start gap-3">
        <StageNumber>1</StageNumber>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 id="dataset-stage-title" className="text-base font-semibold text-foreground">
            Dataset
          </h2>
          <p className="text-sm text-foreground-muted">
            Choose the reviewed questions every candidate will answer.{' '}
            <a
              className="text-accent hover:underline"
              href={docsHref('experiments/datasets')}
              target="_blank"
              rel="noopener noreferrer"
            >
              Dataset import guide
            </a>
          </p>
        </div>
      </div>
      <Label>
        Dataset version
        <NativeSelect
          className="mt-2"
          required
          value={selectedDatasetId}
          onChange={(event) => onDatasetChange(event.target.value)}
        >
          <NativeSelectOption value="">Select reviewed questions</NativeSelectOption>
          {datasets.map((dataset) => (
            <NativeSelectOption key={dataset.id} value={dataset.id}>
              {dataset.name} · v{dataset.version} · {dataset.rows.length} questions
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      <div className="flex flex-col">
        {selectedDataset && (
          <details className="group border-t border-border">
            <summary className={SUMMARY}>
              <ChevronRight aria-hidden="true" className={CHEVRON} />
              Inspect {selectedDataset.rows.length} dataset questions
            </summary>
            <div className="pb-4">
              <Questions rows={selectedDataset.rows} />
            </div>
          </details>
        )}
        <details
          className="group border-t border-border"
          open={importOpen}
          onToggle={(event) => setImportOpen(event.currentTarget.open)}
        >
          <summary className={SUMMARY}>
            <ChevronRight aria-hidden="true" className={CHEVRON} />
            Import a reviewed CSV
          </summary>
          <div className="flex flex-col gap-4 pt-2">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <p className="text-sm text-foreground-muted">
                UTF-8 CSV with a required question column and optional reference answers. Up to{' '}
                {options?.max_rows} questions and {number((options?.max_bytes || 0) / 1024 / 1024)}{' '}
                MiB.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="md:shrink-0"
                onClick={() =>
                  void downloadFile(
                    `/projects/${projectId}/datasets/example.csv`,
                    'example-dataset.csv',
                  ).catch((cause) => setError((cause as Error).message))
                }
              >
                <Download aria-hidden="true" />
                Download example CSV
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Label>
                Dataset name
                <Input
                  className="mt-2"
                  maxLength={120}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Label>
              <Label>
                Version destination
                <NativeSelect
                  className="mt-2"
                  value={identity}
                  onChange={(event) => setIdentity(event.target.value)}
                >
                  <NativeSelectOption value="">Create a new dataset</NativeSelectOption>
                  {datasets
                    .filter(
                      (dataset, index, values) =>
                        values.findIndex((value) => value.dataset_id === dataset.dataset_id) ===
                        index,
                    )
                    .map((dataset) => (
                      <NativeSelectOption key={dataset.dataset_id} value={dataset.dataset_id}>
                        New version of {dataset.name}
                      </NativeSelectOption>
                    ))}
                </NativeSelect>
              </Label>
              <Label className="md:col-span-2">
                CSV file
                <Input
                  className="mt-2 h-auto py-2 pointer-coarse:h-auto"
                  type="file"
                  accept=".csv,text/csv"
                  disabled={busy}
                  onChange={(event) => {
                    request.current += 1;
                    setFile(event.target.files?.[0]);
                    setPreview(undefined);
                  }}
                />
              </Label>
            </div>
            <Button
              variant="outline"
              className="self-start max-md:w-full"
              loading={busy && !preview}
              disabled={!file || busy}
              onClick={() => void loadPreview()}
            >
              Preview CSV
            </Button>
            {error && <InlineError>{error}</InlineError>}
            {preview && (
              <div data-testid="dataset-preview" className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold text-foreground">
                  Preview · {preview.rows.length} questions
                </h3>
                {preview.errors.length > 0 && (
                  <ul
                    role="alert"
                    className="flex list-disc flex-col gap-1 rounded-control border border-danger py-2 pr-4 pl-8 text-sm text-danger"
                  >
                    {preview.errors.map((previewError, index) => (
                      <li key={index}>
                        Row {previewError.row}: {previewError.message}
                      </li>
                    ))}
                  </ul>
                )}
                <Questions rows={preview.rows} />
                <Button
                  className="self-start max-md:w-full"
                  loading={busy}
                  disabled={busy || preview.errors.length > 0 || !name.trim()}
                  onClick={() => void importDataset()}
                >
                  Import reviewed dataset
                </Button>
              </div>
            )}
          </div>
        </details>
      </div>
    </section>
  );
}
