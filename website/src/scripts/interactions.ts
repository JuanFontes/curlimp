// The content and navigation remain usable without JavaScript.
for (const pre of document.querySelectorAll<HTMLElement>('.prose pre')) {
  if (pre.closest('[data-code-block]')) continue;
  const wrapper = document.createElement('div');
  wrapper.className = 'code-block';
  wrapper.dataset.codeBlock = '';
  const toolbar = document.createElement('div');
  toolbar.className = 'code-toolbar';
  const language = document.createElement('span');
  language.textContent = ['bash', 'sh', 'shell'].includes(
    pre.dataset.language || '',
  )
    ? 'Shell'
    : pre.dataset.language || 'Code';
  const button = document.createElement('button');
  button.type = 'button';
  button.dataset.copy = '';
  button.textContent = 'Copy';
  button.setAttribute('aria-label', 'Copy code');
  toolbar.append(language, button);
  pre.before(wrapper);
  wrapper.append(toolbar, pre);
}

for (const button of document.querySelectorAll<HTMLButtonElement>(
  '[data-copy]',
)) {
  button.hidden = false;
  button.addEventListener('click', async () => {
    const code = button.closest('[data-code-block]')?.querySelector('code');
    if (!code) return;
    const original = button.innerHTML;
    try {
      await navigator.clipboard.writeText(code.textContent || '');
      button.textContent = 'Copied!';
      button.setAttribute('aria-label', 'Code copied');
    } catch {
      button.textContent = 'Select to copy';
      const range = document.createRange();
      range.selectNodeContents(code);
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
    }
    window.setTimeout(() => {
      button.innerHTML = original;
      button.setAttribute('aria-label', 'Copy code');
    }, 1800);
  });
}

for (const group of document.querySelectorAll<HTMLElement>('[data-tabs]')) {
  const tabs = [...group.querySelectorAll<HTMLButtonElement>('[data-tab]')];
  const panels = [...group.querySelectorAll<HTMLElement>('[data-panel]')];
  const list = group.querySelector<HTMLElement>('[data-tab-list]')!;
  list.hidden = false;
  list.setAttribute('role', 'tablist');
  const select = (active: number, focus = false) => {
    tabs.forEach((tab, i) => {
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(i === active));
      tab.tabIndex = i === active ? 0 : -1;
      panels[i].hidden = i !== active;
      panels[i].setAttribute('role', 'tabpanel');
      panels[i].setAttribute('aria-labelledby', tab.id);
    });
    if (focus) tabs[active].focus();
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => select(i));
    tab.addEventListener('keydown', (event) => {
      let next: number | undefined;
      if (event.key === 'ArrowRight') next = (i + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (i + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        select(next, true);
      }
    });
  });
  group.classList.add('tabs-enhanced');
  select(0);
}

const menu = document.querySelector<HTMLButtonElement>('.mobile-menu');
const sidebar = document.querySelector<HTMLElement>('.docs-sidebar');
if (menu && sidebar) {
  const main = document.querySelector<HTMLElement>('.doc-main');
  const mobile = window.matchMedia('(max-width: 760px)');
  menu.hidden = false;
  document.documentElement.classList.add('nav-enhanced');
  const close = () => {
    menu.setAttribute('aria-expanded', 'false');
    sidebar.classList.remove('is-open');
    if (main) main.inert = false;
  };
  menu.addEventListener('click', () => {
    const expanded = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(expanded));
    sidebar.classList.toggle('is-open', expanded);
    if (main) main.inert = expanded && mobile.matches;
  });
  mobile.addEventListener('change', close);
  document.addEventListener('keydown', (event) => {
    if (
      event.key === 'Escape' &&
      menu.getAttribute('aria-expanded') === 'true'
    ) {
      close();
      menu.focus();
    }
  });
  sidebar.addEventListener('click', (event) => {
    if ((event.target as HTMLElement).closest('a')) close();
  });
}
