import { useState } from 'react';

import { PlaygroundView } from './components/PlaygroundView';
import { usePlaygroundController, type PlaygroundProps } from './usePlaygroundController';

// Retry after a failed catalog load remounts the Playground, which runs its data hooks again
// with the same route (spec 0002, AC-10).
export function Playground(props: PlaygroundProps) {
  const [attempt, setAttempt] = useState(0);
  return (
    <PlaygroundScreen key={attempt} {...props} onRetry={() => setAttempt((value) => value + 1)} />
  );
}

function PlaygroundScreen({ onRetry, ...props }: PlaygroundProps & { onRetry: () => void }) {
  const view = usePlaygroundController(props);
  return <PlaygroundView {...view} onRetry={onRetry} />;
}
