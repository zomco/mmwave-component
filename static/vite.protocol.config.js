import { resolve } from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: { fs: { allow: [resolve('..')] } },
  build: {
    outDir: process.env.MWCP_BROWSER_OUT || 'dist-protocol-browser',
    emptyOutDir: true,
    rollupOptions: {
      input: resolve('protocol-browser.html'),
    },
  },
});
