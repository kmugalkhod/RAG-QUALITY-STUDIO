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
    <div className="editor-workspace">
      <a className="back-link" href={`#/projects/${projectId}/pipelines`}>
        All pipelines
      </a>
      <div className="editor-title">
        <h1>Pipeline editor</h1>
        <span>Question → grounded answer</span>
      </div>
      {editor.loading && <p role="status">Loading pipeline and server configuration…</p>}
      {editor.error && (
        <p role="alert" className="error-message">
          {editor.error}
        </p>
      )}
      {editor.error && (
        <Button variant="outline" onClick={editor.retry}>
          Retry loading pipeline
        </Button>
      )}
      <fieldset className="pipeline-fields" disabled={editor.busy || editor.loading}>
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
