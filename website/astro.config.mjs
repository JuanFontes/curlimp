import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://juanfontes.github.io',
  base: '/curlimp',
  trailingSlash: 'always',
  output: 'static',
  devToolbar: { enabled: false },
  markdown: {
    shikiConfig: { theme: 'github-dark', wrap: false },
  },
});
