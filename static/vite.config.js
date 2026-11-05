import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { applyInstallerDownloadGuard, assertBundleGuarded } from './script/apply-installer-download-guard.mjs';

applyInstallerDownloadGuard();

const passthroughAssets = [
  '_config.yml',
  'favicon.svg',
  'robots.txt',
  'sitemap.xml',
  'esp32c3',
  'device-artwork',
];

function copyStaticAssets() {
  return {
    name: 'copy-mmwave-static-assets',
    closeBundle() {
      const output = resolve('dist');
      mkdirSync(output, { recursive: true });
      passthroughAssets.forEach((asset) => {
        const source = resolve(asset);
        if (!existsSync(source)) return;
        const destination = resolve(output, asset);
        cpSync(source, destination, { recursive: true });
      });
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [tailwindcss(), copyStaticAssets(), {
    name: 'mmwave-installer-download-guard',
    closeBundle() {
      assertBundleGuarded(resolve('dist'));
    },
  }],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
