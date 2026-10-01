import { Moon, Sun } from 'lucide-react';
import { Button } from '../components/ui/button';
import { useTheme } from './useTheme';

// The header theme switch, shown once every route migrated (spec 0002, build plan step 6).
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const label = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
  return (
    <Button variant="ghost" size="md" icon aria-label={label} title={label} onClick={toggleTheme}>
      {theme === 'dark' ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </Button>
  );
}
