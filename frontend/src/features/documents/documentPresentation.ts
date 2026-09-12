import { type Run } from './model';
export const message = (error: unknown) =>
  error instanceof Error ? error.message : 'Request failed. Please try again.';
export const active = (run: Run | null) => run?.status === 'queued' || run?.status === 'running';
export const date = (value: string) => new Date(value).toLocaleString();
export const bytes = (value: number) => `${new Intl.NumberFormat().format(value)} bytes`;
