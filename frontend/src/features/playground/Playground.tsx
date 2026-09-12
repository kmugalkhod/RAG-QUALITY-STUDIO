import { PlaygroundView } from './components/PlaygroundView';
import { usePlaygroundController, type PlaygroundProps } from './usePlaygroundController';

export function Playground(props: PlaygroundProps) {
  const view = usePlaygroundController(props);
  return <PlaygroundView {...view} />;
}
