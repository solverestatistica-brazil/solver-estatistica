(() => {
  const MEASUREMENT_ID = 'G-KNSPBWRLQD';
  const CONSENT_KEY = 'solver_analytics_consent';
  let loaded = false;

  function readConsent() {
    try { return localStorage.getItem(CONSENT_KEY); } catch (_) { return null; }
  }

  function writeConsent(value) {
    try { localStorage.setItem(CONSENT_KEY, value); } catch (_) { }
  }

  function loadAnalytics() {
    if (loaded || readConsent() !== 'granted') return;
    loaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', MEASUREMENT_ID, {
      anonymize_ip: true,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
    });
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
    document.head.appendChild(script);
  }

  function removeBanner() {
    document.getElementById('analyticsConsent')?.remove();
  }

  function setConsent(value) {
    writeConsent(value);
    removeBanner();
    if (value === 'granted') loadAnalytics();
  }

  function showBanner() {
    if (readConsent() || document.getElementById('analyticsConsent')) return;
    const banner = document.createElement('section');
    banner.id = 'analyticsConsent';
    banner.className = 'consent-banner';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', 'Preferências de métricas');
    banner.innerHTML = `
      <div>
        <strong>Métricas com sua escolha</strong>
        <p>Usamos Google Analytics somente com seu consentimento para entender o uso do Solver. Não usamos esses dados para publicidade.</p>
      </div>
      <div class="consent-actions">
        <a href="privacidade.html">Saiba mais</a>
        <button class="btn ghost" type="button" data-consent="denied">Recusar</button>
        <button class="btn solid" type="button" data-consent="granted">Aceitar métricas</button>
      </div>`;
    banner.querySelectorAll('[data-consent]').forEach((button) => {
      button.addEventListener('click', () => setConsent(button.dataset.consent));
    });
    document.body.appendChild(banner);
  }

  window.SolverAnalytics = {
    accept: () => setConsent('granted'),
    reject: () => setConsent('denied'),
    reset: () => {
      try { localStorage.removeItem(CONSENT_KEY); } catch (_) { }
      window.location.reload();
    },
    status: readConsent,
  };

  if (readConsent() === 'granted') loadAnalytics();
  document.addEventListener('DOMContentLoaded', () => {
    showBanner();
    document.getElementById('resetAnalyticsConsent')?.addEventListener('click', () => {
      window.SolverAnalytics.reset();
    });
  });
})();
