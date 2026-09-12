import { Button } from '../../../components/ui/button';

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
  return (
    <section
      id="save-guidance"
      className="pipeline-validation mt-5 py-3.5 px-4.5"
      aria-label="Graph validation"
      aria-live="polite"
    >
      {saveReasons.length ? (
        <>
          <h2>{alreadySaved ? 'Already saved' : 'To enable Save version'}</h2>
          <ul>
            {saveReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </>
      ) : (
        <p>Ready to save: all five nodes are connected and configured.</p>
      )}
      {needsDocuments && (
        <Button variant="outline" disabled={disabled} onClick={onChooseDocuments}>
          Choose documents to search
        </Button>
      )}
    </section>
  );
}
