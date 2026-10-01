import { CircleCheck, TriangleAlert } from 'lucide-react';
import { LINK } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { docsHref } from '../../../lib/docs';

interface PipelineValidationProps {
  saveReasons: string[];
  alreadySaved: boolean;
  needsDocuments: boolean;
  disabled: boolean;
  onChooseDocuments: () => void;
}

export function PipelineValidation({
  saveReasons,
  alreadySaved,
  needsDocuments,
  disabled,
  onChooseDocuments,
}: PipelineValidationProps) {
  const blocked = saveReasons.length > 0 && !alreadySaved;
  return (
    <section
      id="save-guidance"
      className="flex flex-col gap-2 border-y border-border bg-surface px-4 py-2 md:flex-row md:flex-wrap md:items-center md:justify-between md:px-6"
      aria-label="Graph validation"
      aria-live="polite"
    >
      <div className="flex min-w-0 items-start gap-2 text-sm">
        {blocked ? (
          <TriangleAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
        ) : (
          <CircleCheck aria-hidden="true" className="size-4 shrink-0 text-success" />
        )}
        {saveReasons.length ? (
          <div className="flex min-w-0 flex-col gap-1">
            <h2 className="font-medium text-foreground">
              {alreadySaved ? 'Already saved' : 'To enable Save version'}
            </h2>
            <ul className="flex flex-col gap-1 text-foreground-muted">
              {saveReasons.map((reason) => (
                <li key={reason} className="wrap-anywhere">
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-foreground">
            Ready to save: all five nodes are connected and configured.
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        {needsDocuments && (
          <Button variant="outline" size="sm" disabled={disabled} onClick={onChooseDocuments}>
            Choose documents to search
          </Button>
        )}
        <a
          className={LINK}
          href={docsHref('answers/pipelines')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Answer pipeline setup and validation
        </a>
      </div>
    </section>
  );
}
