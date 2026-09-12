import { Comparison } from './components/Comparison';
import { DatasetImport } from './components/DatasetImport';
import { ExperimentForm } from './components/ExperimentForm';
import { ExperimentHistory } from './components/ExperimentHistory';
import { readDraft, saveDraft, emptyDraft } from './draft';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../../components/ui/button';
import { listPipelines, listPipelineVersions } from '../pipelines/api';
import { type PipelineVersion } from '../pipelines/model';
import { allPages } from '../../lib/pagination';
import * as api from './api';
import { type Dataset, type Experiment, type Metric } from './model';
export function ExperimentsPage({
  projectId,
  experimentId,
}: {
  projectId: string;
  experimentId?: string;
}) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [pipelines, setPipelines] = useState<PipelineVersion[]>([]);
  const [history, setHistory] = useState<Experiment[]>([]);
  const [options, setOptions] = useState<Awaited<ReturnType<typeof api.getEvaluationOptions>>>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [initial] = useState(() => readDraft(projectId));
  const [storageError, setStorageError] = useState('');
  const [dataset, setDataset] = useState(initial.dataset);
  const [a, setA] = useState(initial.a);
  const [b, setB] = useState(initial.b);
  const [selected, setSelected] = useState<Metric[]>(initial.metrics);
  const [name, setName] = useState(initial.name);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    if (experimentId) {
      return;
    }
    setStorageError(
      saveDraft(projectId, { name, dataset, a, b, metrics: selected })
        ? ''
        : 'Draft cannot be stored in this browser. Keep this page open to retain your selections.',
    );
  }, [projectId, experimentId, name, dataset, a, b, selected]);
  function resetDraft() {
    const draft = emptyDraft();
    setName(draft.name);
    setDataset(draft.dataset);
    setA(draft.a);
    setB(draft.b);
    setSelected(draft.metrics);
    setMessage('Experiment draft reset. Saved datasets and runs are unchanged.');
  }
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError('');
    void Promise.all([
      allPages((o) => api.listDatasets(projectId, o)),
      allPages((o) => api.listExperiments(projectId, o)),
      api.getEvaluationOptions(projectId),
      allPages((o) => listPipelines(projectId, o))
        .then((ps) =>
          Promise.all(ps.map((p) => allPages((o) => listPipelineVersions(projectId, p.id, o)))),
        )
        .then((vs) => vs.flat()),
    ])
      .then(([ds, hs, opts, vs]) => {
        if (!disposed) {
          setDatasets(ds);
          setHistory(hs);
          setOptions(opts);
          setPipelines(vs);
          setDataset((id) => (ds.some((d) => d.id === id) ? id : ''));
          setA((id) => (vs.some((v) => v.id === id) ? id : ''));
          setB((id) => (vs.some((v) => v.id === id) ? id : ''));
        }
      })
      .catch((e) => {
        if (!disposed) {
          setError((e as Error).message);
        }
      })
      .finally(() => {
        if (!disposed) {
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await work();
    } catch (e) {
      if (alive.current) {
        setError((e as Error).message);
      }
    } finally {
      if (alive.current) {
        setBusy(false);
      }
    }
  }
  function handleStartExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || options?.error || !dataset || !a || !selected.length || !name.trim()) {
      return;
    }
    void action(async () => {
      const experiment = await api.startExperiment(
        projectId,
        name,
        dataset,
        [a, b].filter(Boolean),
        selected,
      );
      if (alive.current) {
        window.location.hash = `/projects/${projectId}/experiments/${experiment.id}`;
      }
    });
  }

  if (experimentId) {
    return <Comparison projectId={projectId} experimentId={experimentId} />;
  }
  return (
    <section className="experiments max-w-300 my-0 mx-auto">
      <header className="experiment-heading flex items-center justify-between gap-5 mb-5">
        <div>
          <h1>Experiments</h1>
          <p>Compare saved pipelines against the same reviewed questions.</p>
        </div>
      </header>
      {error && (
        <div role="alert">
          {error}{' '}
          <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
            Retry loading
          </Button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {loading ? (
        <p role="status">Loading datasets and saved versions…</p>
      ) : (
        <>
          <DatasetImport
            projectId={projectId}
            datasets={datasets}
            options={options}
            onImported={(imported) => {
              setDataset(imported.id);
              setMessage(`Imported ${imported.name} version ${imported.version}.`);
              setRevision((value) => value + 1);
            }}
          />
          <ExperimentForm
            projectId={projectId}
            datasets={datasets}
            pipelines={pipelines}
            options={options}
            name={name}
            datasetId={dataset}
            candidateA={a}
            candidateB={b}
            selectedMetrics={selected}
            busy={busy}
            storageError={storageError}
            onNameChange={setName}
            onDatasetChange={setDataset}
            onCandidateAChange={setA}
            onCandidateBChange={setB}
            onMetricsChange={setSelected}
            onReset={resetDraft}
            onSubmit={handleStartExperiment}
          />
          <ExperimentHistory projectId={projectId} experiments={history} />
        </>
      )}
    </section>
  );
}
