import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';

const passthroughAssets = [
  '_config.yml',
  'favicon.svg',
  'hero.jpg',
  'hero_rebranded.png',
  'models.preview.json',
  'robots.txt',
  'sitemap.xml',
  'esp32c3',
  'esp32s3',
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
  plugins: [copyStaticAssets()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
