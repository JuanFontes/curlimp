import cargo from '../../../Cargo.toml?raw';
import profileSource from '../../../src/profiles.txt?raw';
import helpSource from '../../../src/help.txt?raw';

export const repository = 'https://github.com/JuanFontes/curlimp';
export const dockerHub = 'https://hub.docker.com/r/juanfontes/curlimp';
export const origin = 'https://juanfontes.github.io';
export const base = import.meta.env.BASE_URL.replace(/\/$/, '');
export const href = (path = '') =>
  `${base}/${path.replace(/^\/+|\/+$/g, '')}${path ? '/' : ''}`;
export const absolute = (path = '') => new URL(href(path), origin).href;
export const version = cargo.match(/^version\s*=\s*"([^"]+)"/m)![1];
export const release = `${repository}/releases/tag/v${version}`;
export const image = 'juanfontes/curlimp:latest';
export const versionedImage = `juanfontes/curlimp:${version}`;
export const profiles = profileSource
  .split('\n')
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith('#'));
export const cliHelp = helpSource;

export const groups = [
  {
    label: 'Documentation',
    pages: [
      { slug: '', title: 'Introduction' },
      { slug: 'why', title: 'Why this project' },
    ],
  },
  {
    label: 'Getting started',
    pages: [
      { slug: 'quick-start', title: 'Quick start' },
      { slug: 'installation', title: 'Installation' },
      { slug: 'docker', title: 'Docker' },
    ],
  },
  {
    label: 'Usage',
    pages: [
      { slug: 'profiles', title: 'Browser profiles' },
      { slug: 'completion', title: 'Zsh autocomplete' },
      { slug: 'body-and-headers', title: 'Body & headers' },
      { slug: 'redirects-and-status', title: 'Redirects & status codes' },
      { slug: 'requests', title: 'Requests & JSON' },
      { slug: 'authentication-and-cookies', title: 'Authentication & cookies' },
      { slug: 'files', title: 'Files & pipelines' },
      { slug: 'response-exports', title: 'TXT & JSON exports' },
      { slug: 'networking', title: 'Networking & diagnostics' },
      { slug: 'cli-reference', title: 'CLI reference' },
    ],
  },
  {
    label: 'Under the hood',
    pages: [
      { slug: 'architecture', title: 'Architecture' },
      { slug: 'building', title: 'Building from source' },
      { slug: 'compatibility', title: 'Compatibility & limits' },
    ],
  },
];
export const pages = groups.flatMap((group) => group.pages);
export const docHref = (slug = '') => href(`docs${slug ? `/${slug}` : ''}`);

export const firstRequest = `docker run --rm \\\n  ${image} \\\n  -sS -I https://httpbin.org/status/200`;
