import { resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { applyInstallerDownloadGuard, assertBundleGuarded } from './script/apply-installer-download-guard.mjs';

applyInstallerDownloadGuard();
const appOutDir = process.env.MWCP_APP_OUT || resolve('dist-app-browser');

export default defineConfig({
  base: './',
  plugins: [tailwindcss(), {
    name: 'mmwave-installer-download-guard',
    closeBundle() {
      assertBundleGuarded(appOutDir);
    },
  }],
  resolve: {
    alias: {
      'node:crypto': resolve('test/browser/sha256-shim.js'),
    },
  },
  server: { fs: { allow: [resolve('..')] } },
  build: {
    outDir: appOutDir,
    emptyOutDir: true,
    minify: false,
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve('app-browser.html'),
    },
  },
});
