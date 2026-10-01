import type { ComponentProps } from 'react';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowNode } from '../../../src/features/pipelines/components/WorkflowNode';
import type { PipelineNodeConfig } from '../../../src/features/pipelines/model';

// covers: AC-9 (node card label, summary line, selection). The Tooltip hover is a browser check:
// Radix tooltips keep jsdom's event loop busy for seconds once opened.

type NodeProps = ComponentProps<typeof WorkflowNode>;

function renderNode(config: PipelineNodeConfig, { selected = false, label = 'Retriever' } = {}) {
  const props = {
    id: config.id,
    type: 'workflow',
    data: { label, config, vertical: true },
    selected,
    dragging: false,
    zIndex: 0,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    draggable: true,
    selectable: true,
    deletable: false,
  } as NodeProps;
  return render(
    <ReactFlowProvider>
      <WorkflowNode {...props} />
    </ReactFlowProvider>,
  );
}

test('the card shows the node label and its one line summary', () => {
  renderNode({ id: 'r', type: 'retriever' });
  expect(screen.getByText('Retriever')).toBeVisible();
  expect(screen.getByText('Vector · Top 5 · Choose documents')).toBeVisible();
});

test('the card reports whether it is selected', () => {
  const { unmount } = renderNode({ id: 'a', type: 'answer' }, { label: 'Answer' });
  expect(screen.getByTestId('node-card')).toHaveAttribute('data-selected', 'false');
  unmount();
  renderNode({ id: 'a', type: 'answer' }, { label: 'Answer', selected: true });
  expect(screen.getByTestId('node-card')).toHaveAttribute('data-selected', 'true');
});
