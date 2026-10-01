import { RefreshCw } from 'lucide-react';
import { LIST, LIST_ROW, META } from '../../../components/parts';
import { Pagination } from '../../../components/Pagination';
import { Button } from '../../../components/ui/button';
import { docsHref } from '../../../lib/docs';

import { type QueryRun } from '../model';
interface Props {
  runs: QueryRun[];
  total: number;
  offset: number;
  running: boolean;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onSelect: (run: QueryRun) => void;
}
export function RunHistory({ runs, total, offset, running, onRefresh, onPage, onSelect }: Props) {
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <a
          className="text-sm text-accent hover:underline"
          href={docsHref('answers/history')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Query history guide
        </a>
        <Button variant="outline" size="sm" disabled={!!running} onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </Button>
      </div>
      {!runs.length ? (
        <p className="text-sm text-foreground-muted">No saved questions yet.</p>
      ) : (
        <ul className={LIST}>
          {runs.map((item) => (
            <li key={item.id} className={`${LIST_ROW} flex flex-col gap-1 px-2 py-2`}>
              <Button
                variant="ghost"
                className="h-auto min-h-row justify-start px-2 py-2 text-left whitespace-normal pointer-coarse:h-auto [&>span]:line-clamp-2"
                disabled={!!running}
                onClick={() => onSelect(item)}
              >
                <span>{item.question}</span>
              </Button>
              <p className={`${META} px-2`}>
                {item.snapshot.pipeline_preview
                  ? 'Test draft'
                  : item.pipeline_version_id
                    ? `Pipeline v${item.snapshot.pipeline_version}`
                    : 'Default settings'}{' '}
                · {item.status.replaceAll('_', ' ')}
              </p>
            </li>
          ))}
        </ul>
      )}
      <Pagination
        offset={offset}
        total={total}
        onChange={onPage}
        busy={running}
        label="Query history pages"
        previousLabel="Previous queries"
        nextLabel="Next queries"
      />
    </div>
  );
}
