import { resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  plugins: [tailwindcss()],
  resolve: {
    alias: {
      'node:crypto': resolve('test/browser/sha256-shim.js'),
    },
  },
  server: { fs: { allow: [resolve('..')] } },
  build: {
    outDir: process.env.MWCP_APP_OUT || 'dist-app-browser',
    emptyOutDir: true,
    minify: false,
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve('app-browser.html'),
    },
  },
});
