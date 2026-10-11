# Documentation website

The public site is built with Astro as static HTML for [GitHub Pages](https://juanfontes.github.io/curlimp/). It has no runtime backend, client-side routing requirement, analytics or remote-font dependency.

## Develop

Use Node.js 22.12 or newer (CI uses Node 24), npm and Python 3:

```sh
cd website
npm ci
npm run dev
```

Open the base-prefixed URL printed by Astro. To check the production output:

```sh
npm run build
npm run check
npm run preview
```

`check` validates local links and anchors, metadata, the sitemap, profile coverage and documentation example URLs. Inspect desktop and mobile navigation, tabs and copy controls after UI changes. No native engine rebuild is needed for site-only edits.

Run `npm run format` after source edits. CI checks formatting with `npm run format:check`.

## Content and structure

- `src/pages/index.astro`: project homepage.
- `src/pages/docs/`: Markdown guides and data-driven reference pages.
- `src/layouts/`: document shell and shared page metadata.
- `src/components/`: header, code blocks and Tabler icons.
- `src/lib/site.ts`: navigation and repository data. Version, profile catalog and CLI help come from the CLI sources at build time.
- `src/styles/`: visual system and responsive layouts.
- `src/scripts/`: progressive enhancement for copy controls, tabs and mobile navigation.

Use status endpoints in public request examples. Explain empty bodies, intentional error statuses and the fact that status fixtures do not validate payloads or credentials. Keep the CLI's documented limits explicit.

The original visual system uses Inter and JetBrains Mono (SIL Open Font License), with Tabler icons (MIT). Their notices are preserved in `public/THIRD-PARTY-NOTICES.txt` and shipped with the static site. Keep this file in sync when updating those packages. `public/social.png` is the 1200 × 630 raster export of `public/social.svg`; keep both in sync when changing the sharing graphic. Page content is HTML, not a screenshot.

## Publish

The Pages workflow validates builds on pushes and pull requests. Deployment stays disabled until the repository Actions variable `PAGES_ENABLED` is set to `true`. Use **GitHub Actions** as the repository's Pages source and set that variable; successful builds on `main` then deploy. Forks can leave the variable unset to build without deploying. `astro.config.mjs` fixes the production origin and `/curlimp` base. Change both deliberately when changing the domain, then check canonical URLs, internal links, share metadata and sitemap.

The runtime workflow ignores website and public documentation edits. It still runs for engine, CLI, packaging and runtime-workflow changes.

## Search and indexing

Every page emits static content, a descriptive title, unique description, canonical URL, Open Graph metadata and JSON-LD. The homepage describes the software source; documentation uses breadcrumbs. No fabricated reviews or ratings are included. `404.html` is marked `noindex`; it is excluded from the sitemap.

The generated sitemap is at `https://juanfontes.github.io/curlimp/sitemap.xml`. Submit it in a verified Google Search Console or Bing Webmaster Tools property if desired. Publishing a sitemap does not guarantee indexing or search position.

Crawler rules in `robots.txt` are read at the **origin root**, not the project subdirectory. This repository does not control `https://juanfontes.github.io/robots.txt`, so it intentionally does not publish a misleading project-path robots file. The site itself has no crawl-blocking or noindex directive on its content pages. If a root-site robots policy is introduced, ensure it allows the project path and its assets and points to this sitemap.
