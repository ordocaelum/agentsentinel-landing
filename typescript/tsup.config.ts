import { defineConfig } from 'tsup';

export default defineConfig({
  entry: ['src/index.ts', 'src/integrations/*.ts'],
  format: ['cjs', 'esm'],
  dts: true,
  clean: true,
  splitting: false,
  sourcemap: true,
});
