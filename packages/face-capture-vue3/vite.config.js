import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { readFileSync } from 'node:fs';

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'include-component-styles',
      generateBundle(_options, bundle) {
        const entry = bundle['index.js'];
        if (!entry || entry.type !== 'chunk') throw new Error('Missing library entry');
        entry.code = `import './style.css';\n${entry.code}`;
        this.emitFile({
          type: 'asset',
          fileName: 'index.d.ts',
          source: readFileSync(new URL('./src/index.d.ts', import.meta.url))
        });
      }
    }
  ],
  build: {
    lib: {
      entry: 'src/index.js',
      formats: ['es'],
      fileName: 'index',
      cssFileName: 'style'
    },
    rollupOptions: { external: ['vue'] }
  }
});
