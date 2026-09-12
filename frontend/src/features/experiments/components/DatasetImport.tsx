import { useRef, useState } from 'react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { number } from '../format';
import type { Dataset, Preview } from '../model';
import * as api from '../api';
import { Questions } from './Questions';

type EvaluationOptions = Awaited<ReturnType<typeof api.getEvaluationOptions>>;

export function DatasetImport({
  projectId,
  datasets,
  options,
  onImported,
}: {
  projectId: string;
  datasets: Dataset[];
  options?: EvaluationOptions;
  onImported: (dataset: Dataset) => void;
}) {
  const request = useRef(0);
  const [file, setFile] = useState<File>();
  const [name, setName] = useState('');
  const [identity, setIdentity] = useState('');
  const [preview, setPreview] = useState<Preview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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

  return (
    <details
      className="experiment-section mt-6 border-t border-border py-6"
      open={!datasets.length}
    >
      <summary>Import evaluation dataset</summary>
      <p>
        UTF-8 CSV with a required question column and optional reference answers. Up to{' '}
        {options?.max_rows} questions and {number((options?.max_bytes || 0) / 1024 / 1024)} MiB.
      </p>
      <a href={`/api/projects/${projectId}/datasets/example.csv`} download>
        Download example CSV
      </a>
      <div className="experiment-fields my-5 grid grid-cols-2 gap-5">
        <Label>
          Dataset name
          <Input maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
        </Label>
        <Label>
          Version destination
          <NativeSelect value={identity} onChange={(event) => setIdentity(event.target.value)}>
            <NativeSelectOption value="">Create a new dataset</NativeSelectOption>
            {datasets
              .filter(
                (dataset, index, values) =>
                  values.findIndex((value) => value.dataset_id === dataset.dataset_id) === index,
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
        <div className="mt-6">
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
    </details>
  );
}
