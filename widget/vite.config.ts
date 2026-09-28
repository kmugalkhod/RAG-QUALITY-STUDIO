import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import fs from 'node:fs/promises';

const api = process.env.WIDGET_API_ORIGIN || 'http://127.0.0.1:8000';
const framePath = /^\/v1\.0\.0\/frame\/([0-9a-fA-F-]{36})$/;

export default defineConfig({
  plugins: [react(), {
    name: 'widget-frame-csp',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const match = framePath.exec((req.url || '').split('?')[0]);
        if (!match) return next();
        try {
          const configResponse = await fetch(`${api}/v1/answer-deployments/${match[1]}/widget/config`);
          if (!configResponse.ok) throw new Error('Unknown deployment');
          const config = await configResponse.json() as { allowed_origins: string[] };
          const preview = new URL(req.url || '/', 'http://127.0.0.1:5274').searchParams.get('preview') === '1';
          const ancestors = [...config.allowed_origins, ...(preview ? ['http://127.0.0.1:5273', 'http://localhost:5273'] : [])].join(' ') || "'none'";
          res.setHeader('Content-Security-Policy', `default-src 'none'; frame-ancestors ${ancestors}; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' ${api}; img-src 'self' data:; base-uri 'none'; form-action 'none'`);
          res.setHeader('Cache-Control', 'no-store');
          res.setHeader('Referrer-Policy', 'no-referrer');
          res.setHeader('Content-Type', 'text/html; charset=utf-8');
          const html = await fs.readFile('frame.html', 'utf8');
          res.end(await server.transformIndexHtml(req.url || '/', html));
        } catch {
          res.statusCode = 404;
          res.end('Widget unavailable');
        }
      });
    },
  }],
  server: { port: 5274, strictPort: true, host: '127.0.0.1' },
  build: { rollupOptions: { input: 'frame.html' }, assetsDir: 'v1.0.0/assets', outDir: 'dist' },
  test: { environment: 'jsdom', include: ['tests/**/*.test.{ts,js}'] },
});
