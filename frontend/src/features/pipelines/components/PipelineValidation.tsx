import { TriangleAlert } from 'lucide-react';
import { Button } from '../../../components/ui/button';

interface PipelineValidationProps {
  id: string;
  saveReasons: string[];
  needsDocuments: boolean;
  disabled: boolean;
  onChooseDocuments: () => void;
}

// Shown only while something blocks Save; the toolbar badge already reports the saved state.
export function PipelineValidation({
  id,
  saveReasons,
  needsDocuments,
  disabled,
  onChooseDocuments,
}: PipelineValidationProps) {
  return (
    <section
      id={id}
      className="flex flex-col gap-2 border-t border-border bg-surface px-4 py-2 md:flex-row md:items-center md:justify-between md:px-6"
      aria-label="Graph validation"
      aria-live="polite"
    >
      <div className="flex min-w-0 items-start gap-2 text-sm">
        <TriangleAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="font-medium text-foreground">To enable Save version</h2>
          <ul className="flex flex-col gap-1 text-foreground-muted">
            {saveReasons.map((reason) => (
              <li key={reason} className="wrap-anywhere">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {needsDocuments && (
        <Button variant="outline" size="sm" disabled={disabled} onClick={onChooseDocuments}>
          Choose documents to search
        </Button>
      )}
    </section>
  );
}
