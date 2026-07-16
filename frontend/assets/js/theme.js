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
      if (icon) icon.textContent = isLight ? '☾' : '☀';
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
