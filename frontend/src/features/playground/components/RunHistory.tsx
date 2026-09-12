import { Button } from '../../../components/ui/button';
import { Pagination } from '../../../components/Pagination';

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
    <div className="playground-history">
      <section aria-labelledby="history-title">
        <div className="section-heading flex justify-between items-center gap-2.5 m-0 py-4 px-7">
          <h2 id="history-title">Past questions</h2>
          <Button variant="outline" disabled={!!running} onClick={onRefresh}>
            Refresh
          </Button>
        </div>
        {!runs.length && <p>No saved questions yet.</p>}
        <ul className="document-list">
          {runs.map((item) => (
            <li key={item.id}>
              <div>
                <Button
                  variant="ghost"
                  className="document-name h-auto min-h-0 justify-start whitespace-normal border-0 bg-transparent p-0 text-left text-foreground wrap-anywhere text-xs leading-normal font-medium"
                  disabled={!!running}
                  onClick={() => onSelect(item)}
                >
                  {item.question}
                </Button>
                <p>
                  {item.snapshot.pipeline_preview
                    ? 'Test draft'
                    : item.pipeline_version_id
                      ? `Pipeline v${item.snapshot.pipeline_version}`
                      : 'Default settings'}{' '}
                  · {item.status.replaceAll('_', ' ')}
                </p>
              </div>
            </li>
          ))}
        </ul>
        <Pagination
          offset={offset}
          total={total}
          onChange={onPage}
          busy={running}
          label="Query history pages"
          previousLabel="Previous queries"
          nextLabel="Next queries"
        />
      </section>
    </div>
  );
}
