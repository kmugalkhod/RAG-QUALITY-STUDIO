import { useRef, useState } from 'react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { number } from '../format';
import type { Dataset, Preview } from '../model';
import * as api from '../api';
import { Questions } from './Questions';
import { docsHref } from '../../../lib/docs';

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
    <section className="experiment-stage" aria-labelledby="dataset-stage-title">
      <div className="experiment-stage-heading">
        <span className="experiment-stage-index" aria-hidden="true">
          1
        </span>
        <div>
          <h2 id="dataset-stage-title">Dataset</h2>
          <p>Choose the reviewed questions every candidate will answer.</p>
          <a href={docsHref('experiments/datasets')} target="_blank" rel="noopener noreferrer">
            Dataset import guide
          </a>
        </div>
      </div>
      <Label className="dataset-version-field">
        Dataset version
        <NativeSelect
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
      {selectedDataset && (
        <details className="dataset-questions">
          <summary>Inspect {selectedDataset.rows.length} dataset questions</summary>
          <Questions rows={selectedDataset.rows} />
        </details>
      )}
      <details
        className="dataset-import"
        open={importOpen}
        onToggle={(event) => setImportOpen(event.currentTarget.open)}
      >
        <summary>Import a reviewed CSV</summary>
        <div className="dataset-import-body">
          <p>
            UTF-8 CSV with a required question column and optional reference answers. Up to{' '}
            {options?.max_rows} questions and {number((options?.max_bytes || 0) / 1024 / 1024)} MiB.
          </p>
          <a href={`/api/projects/${projectId}/datasets/example.csv`} download>
            Download example CSV
          </a>
          <div className="experiment-fields">
            <Label>
              Dataset name
              <Input
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Label>
            <Label>
              Version destination
              <NativeSelect value={identity} onChange={(event) => setIdentity(event.target.value)}>
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
            <Label>
              CSV file
              <Input
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
          <Button variant="outline" disabled={!file || busy} onClick={() => void loadPreview()}>
            {busy ? 'Reading…' : 'Preview CSV'}
          </Button>
          {error && <p role="alert">{error}</p>}
          {preview && (
            <div className="dataset-preview">
              <h3>Preview · {preview.rows.length} questions</h3>
              {preview.errors.length > 0 && (
                <ul role="alert">
                  {preview.errors.map((previewError, index) => (
                    <li key={index}>
                      Row {previewError.row}: {previewError.message}
                    </li>
                  ))}
                </ul>
              )}
              <Questions rows={preview.rows} />
              <Button
                disabled={busy || preview.errors.length > 0 || !name.trim()}
                onClick={() => void importDataset()}
              >
                Import reviewed dataset
              </Button>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
