import { absolute, pages } from '../lib/site';

export function GET() {
  const urls = [
    absolute(),
    ...pages.map((page) => absolute(`docs${page.slug ? `/${page.slug}` : ''}`)),
  ];
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((url) => `  <url><loc>${url}</loc></url>`).join('\n')}\n</urlset>\n`;
  return new Response(body, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
