import { useEffect, useState } from 'react';
import * as api from './api';
import type { QueryRun } from './model';

export function useRunHistory(projectId: string, completedRuns: number) {
  const [runs, setRuns] = useState<QueryRun[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  useEffect(() => {
    let disposed = false;
    void api
      .listRuns(projectId, offset)
      .then((page) => {
        if (!disposed) {
          setRuns(page.items);
          setTotal(page.total);
          setError('');
        }
      })
      .catch((cause) => {
        if (!disposed) {
          setError((cause as Error).message);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, offset, revision, completedRuns]);
  return {
    runs,
    total,
    offset,
    error,
    setOffset,
    refresh: () => setRevision((value) => value + 1),
  };
}
