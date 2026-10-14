import { useCallback, useEffect, useRef, useState } from 'react';

import * as api from './api';
import { requestErrorMessage } from './editorModel';
import type { SettingRecommendation, WebsiteSelection } from './model';

const POLL_MS = 1000;

const active = (recommendation?: SettingRecommendation) =>
  recommendation?.status === 'queued' || recommendation?.status === 'running';

/**
 * One Website source's recommended-settings analysis (spec 0011): start it, then poll
 * sequentially (one request at a time, every second) until it ends. Responses for an
 * analysis that was replaced, or that arrive after unmount, are ignored.
 */
export function useWebsiteRecommendation(projectId: string, nodeId: string) {
  const [recommendation, setRecommendation] = useState<SettingRecommendation>();
  const [error, setError] = useState('');
  const generation = useRef(0);
  const polling = active(recommendation);

  useEffect(() => {
    if (!recommendation || !polling) {
      return;
    }
    let disposed = false;
    const ticket = generation.current;
    const timer = window.setTimeout(() => {
      api
        .getSettingRecommendation(projectId, recommendation.id)
        .then((next) => {
          if (!disposed && ticket === generation.current) {
            setRecommendation(next);
          }
        })
        .catch((cause) => {
          if (!disposed && ticket === generation.current) {
            setError(requestErrorMessage(cause));
          }
        });
    }, POLL_MS);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [projectId, recommendation, polling]);

  const start = useCallback(
    async (selection: WebsiteSelection, otherSourcesMaxPages: number, refresh = false) => {
      generation.current += 1;
      const ticket = generation.current;
      setError('');
      try {
        const next = await api.startSettingRecommendation(projectId, {
          target: 'website',
          source_node_id: nodeId,
          selection,
          other_sources_max_pages: otherSourcesMaxPages,
          refresh,
        });
        if (ticket === generation.current) {
          setRecommendation(next);
        }
      } catch (cause) {
        if (ticket === generation.current) {
          setError(requestErrorMessage(cause));
        }
      }
    },
    [projectId, nodeId],
  );

  return { recommendation, error, analysing: polling, start };
}
