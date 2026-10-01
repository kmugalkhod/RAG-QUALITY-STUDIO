import { ArrowLeft } from 'lucide-react';
import { PageHeader } from '../../components/PageHeader';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { Button } from '../../components/ui/button';
import { NodeSettings } from './components/NodeSettings';
import { PipelineCanvas } from './components/PipelineCanvas';
import { PipelineToolbar } from './components/PipelineToolbar';
import { PipelineValidation } from './components/PipelineValidation';
import { usePipelineEditor } from './usePipelineEditor';

export function PipelineEditor({
  projectId,
  pipelineId,
  versionId = '',
}: {
  projectId: string;
  pipelineId: string;
  versionId?: string;
}) {
  const editor = usePipelineEditor(projectId, pipelineId, versionId);
  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex flex-col gap-4 px-4 pt-4 pb-6 md:px-6">
        <Button variant="ghost" size="sm" className="-ml-2 self-start" asChild>
          <a href={`#/projects/${projectId}/pipelines`}>
            <ArrowLeft aria-hidden="true" />
            All pipelines
          </a>
        </Button>
        <PageHeader title="Pipeline editor" meta="Question → grounded answer" />
        {editor.loading && (
          <LoadingState label="Loading pipeline and server configuration…" rows={2} />
        )}
        {editor.error && (
          <ErrorState
            title="The pipeline request failed"
            message={editor.error}
            onRetry={editor.retry}
            retryLabel="Retry loading pipeline"
          />
        )}
      </div>
      <fieldset
        className="m-0 flex min-w-0 flex-col border-0 p-0"
        disabled={editor.busy || editor.loading}
      >
        <div className="px-4 pb-6 md:px-6">
          <PipelineToolbar
            name={editor.name}
            saved={editor.saved}
            versions={editor.versions}
            dirty={editor.dirty}
            busy={editor.busy}
            canSave={editor.saveReasons.length === 0}
            onNameChange={editor.setName}
            onVersionSelect={editor.open}
            onSave={editor.save}
            onDuplicate={editor.duplicate}
            onDiscard={editor.discard}
            onOpenPlayground={editor.openPlayground}
          />
        </div>
        <PipelineValidation
          saveReasons={editor.saveReasons}
          alreadySaved={!!editor.saved && !editor.dirty && !editor.loading && !editor.busy}
          needsDocuments={editor.errors.some((reason) => reason.startsWith('Retriever: choose'))}
          disabled={editor.busy || editor.loading}
          onChooseDocuments={editor.chooseDocuments}
        />
        <PipelineCanvas
          nodes={editor.nodes}
          edges={editor.edges}
          flow={editor.flow}
          busy={editor.busy}
          inspectorOpen={editor.inspectorOpen}
          onInit={editor.setFlow}
          onNodesChange={editor.changeNodes}
          onEdgesChange={editor.onEdgesChange}
          onConnect={editor.connect}
          onNodeSelect={(nodeId) => editor.selectNode(nodeId, false)}
          onAddNode={editor.addNode}
          onArrange={editor.arrange}
          onRestoreTemplate={editor.restoreTemplate}
          onInspectorOpenChange={editor.setInspectorOpen}
        >
          <NodeSettings
            open={editor.inspectorOpen}
            config={editor.config}
            selected={editor.selected}
            nodes={editor.nodes}
            indexes={editor.indexes}
            options={editor.options}
            onSelect={editor.selectNode}
            onUpdate={editor.updateNode}
            onDelete={editor.removeNode}
          />
        </PipelineCanvas>
      </fieldset>
    </div>
  );
}
