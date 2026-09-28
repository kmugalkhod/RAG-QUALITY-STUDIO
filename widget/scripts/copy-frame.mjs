import { cp, mkdir } from 'node:fs/promises';
await mkdir('dist/v1.0.0', { recursive: true });
await cp('dist/frame.html', 'dist/v1.0.0/frame.html');
