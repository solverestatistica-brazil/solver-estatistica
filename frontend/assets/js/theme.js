(() => {
  const STORAGE_KEY = 'solver_theme';
  const root = document.documentElement;

  function savedTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
    } catch (_) {
      return 'dark';
    }
  }

  function updateControls(theme) {
    const isLight = theme === 'light';
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const label = button.querySelector('[data-theme-label]');
      const icon = button.querySelector('[data-theme-icon]');
      button.setAttribute('aria-pressed', String(isLight));
      button.setAttribute('aria-label', isLight ? 'Ativar tema escuro' : 'Ativar tema claro');
      if (label) label.textContent = isLight ? 'Escuro' : 'Claro';
      if (icon) icon.innerHTML = isLight
        ? '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.2 6.2 0 0 0 10.5 10.5z"/></svg>'
        : '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.1M12 19.3v2.1M4.7 4.7l1.5 1.5M17.8 17.8l1.5 1.5M2.6 12h2.1M19.3 12h2.1M4.7 19.3l1.5-1.5M17.8 6.2l1.5-1.5"/></svg>';
    });
  }

  function applyTheme(theme, persist = true) {
    const nextTheme = theme === 'light' ? 'light' : 'dark';
    root.dataset.theme = nextTheme;
    root.style.colorScheme = nextTheme;

    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = nextTheme === 'light' ? '#F4F7F2' : '#0A0A0A';

    if (persist) {
      try { localStorage.setItem(STORAGE_KEY, nextTheme); } catch (_) { }
    }

    updateControls(nextTheme);
    window.dispatchEvent(new CustomEvent('solver-theme-change', { detail: { theme: nextTheme } }));
  }

  function bindControls() {
    updateControls(root.dataset.theme || 'dark');
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.addEventListener('click', () => {
        applyTheme(root.dataset.theme === 'light' ? 'dark' : 'light');
      });
    });
  }

  applyTheme(savedTheme(), false);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindControls, { once: true });
  } else {
    bindControls();
  }

  window.SolverTheme = {
    get: () => root.dataset.theme || 'dark',
    set: (theme) => applyTheme(theme),
    toggle: () => applyTheme(root.dataset.theme === 'light' ? 'dark' : 'light')
  };
})();
