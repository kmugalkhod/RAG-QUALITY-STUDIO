import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
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
  // Loading and busy reasons are momentary; the strip appears only for fixes the user must make.
  const showGuidance =
    editor.saveReasons.length > 0 &&
    !editor.loading &&
    !editor.busy &&
    !(editor.saved && !editor.dirty);
  return (
    <div className="flex min-w-0 flex-col">
      <h1 className="sr-only">Pipeline editor</h1>
      {(editor.loading || editor.error) && (
        <div className="flex flex-col gap-4 px-4 pt-4 md:px-6">
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
      )}
      <fieldset
        className="m-0 flex min-w-0 flex-col border-0 p-0"
        disabled={editor.busy || editor.loading}
      >
        <div className="px-4 py-3 md:px-6">
          <PipelineToolbar
            backHref={`#/projects/${projectId}/pipelines`}
            name={editor.name}
            saved={editor.saved}
            versions={editor.versions}
            dirty={editor.dirty}
            busy={editor.busy}
            canSave={editor.saveReasons.length === 0}
            guidanceId={showGuidance ? 'save-guidance' : undefined}
            onNameChange={editor.setName}
            onVersionSelect={editor.open}
            onSave={editor.save}
            onDuplicate={editor.duplicate}
            onDiscard={editor.discard}
            onOpenPlayground={editor.openPlayground}
          />
        </div>
        {showGuidance && (
          <PipelineValidation
            id="save-guidance"
            saveReasons={editor.saveReasons}
            needsDocuments={editor.errors.some((reason) => reason.startsWith('Retriever: choose'))}
            disabled={editor.busy || editor.loading}
            onChooseDocuments={editor.chooseDocuments}
          />
        )}
        <PipelineCanvas
          nodes={editor.flowNodes}
          edges={editor.edges}
          flow={editor.flow}
          layoutKey={editor.layoutKey}
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
            optionsLoading={editor.optionsLoading}
            onRefreshOptions={editor.refreshOptions}
            onSelect={editor.selectNode}
            onUpdate={editor.updateNode}
            onDelete={editor.removeNode}
          />
        </PipelineCanvas>
      </fieldset>
    </div>
  );
}
