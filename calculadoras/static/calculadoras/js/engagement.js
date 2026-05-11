/* engagement.js — Banner contextual al ERP tras N cálculos.
 *
 * Cuenta cálculos en localStorage. Tras alcanzar el umbral, muestra una vez
 * un toast/banner sugerendo el ERP. Se puede descartar para no insistir.
 *
 * Storage:
 *   calc_engagement = { n: 0, dismissed: false, last_seen: 0 }
 */
(function () {
  const KEY = 'calc_engagement';
  const UMBRAL = 3;          // mostrar tras 3 cálculos
  const COOLDOWN_DAYS = 7;   // si se descartó, volver a mostrar tras 7 días

  function _read() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : { n: 0, dismissed: false, last_seen: 0 };
    } catch { return { n: 0, dismissed: false, last_seen: 0 }; }
  }

  function _write(d) {
    try { localStorage.setItem(KEY, JSON.stringify(d)); }
    catch { /* private mode */ }
  }

  function _shouldShow(state) {
    if (state.n < UMBRAL) return false;
    if (!state.dismissed) return true;
    const elapsed_days = (Date.now() - (state.last_seen || 0)) / 86400000;
    return elapsed_days > COOLDOWN_DAYS;
  }

  function _showBanner() {
    if (document.getElementById('engagement-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'engagement-banner';
    banner.setAttribute('role', 'dialog');
    banner.style.cssText = 'position:fixed;bottom:16px;right:16px;max-width:380px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;padding:16px 18px;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,0.3);z-index:60;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;animation:engSlide 0.4s ease;';
    banner.innerHTML = `
      <style>@keyframes engSlide { from { transform: translateY(20px); opacity: 0 } to { transform: translateY(0); opacity: 1 } }</style>
      <div style="display:flex;align-items:flex-start;gap:12px;">
        <div style="font-size:24px;line-height:1;">⚡</div>
        <div style="flex:1;">
          <div style="font-weight:700;font-size:14px;margin-bottom:4px;">¿Haces estos cálculos seguido?</div>
          <div style="font-size:12px;color:#cbd5e1;line-height:1.45;margin-bottom:10px;">FácilGestión automatiza IVA, libros contables y boletas desde tus facturas reales del SII.</div>
          <div style="display:flex;gap:8px;">
            <a href="https://gestion.facilgestion.cl" target="_blank" rel="noopener"
               style="background:white;color:#0f172a;text-decoration:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;">Conocer →</a>
            <button id="eng-dismiss" style="background:transparent;color:#94a3b8;border:0;padding:6px 8px;font-size:12px;cursor:pointer;">No, gracias</button>
          </div>
        </div>
        <button id="eng-close" style="background:transparent;color:#64748b;border:0;padding:0;cursor:pointer;font-size:18px;line-height:1;">×</button>
      </div>
    `;
    document.body.appendChild(banner);

    function _dismiss() {
      const s = _read();
      s.dismissed = true;
      s.last_seen = Date.now();
      _write(s);
      banner.remove();
    }
    document.getElementById('eng-close').addEventListener('click', _dismiss);
    document.getElementById('eng-dismiss').addEventListener('click', _dismiss);
  }

  // API pública: una calc llama a window.engagement.tick() después de calcular.
  window.engagement = {
    tick() {
      const s = _read();
      s.n += 1;
      _write(s);
      if (_shouldShow(s)) {
        setTimeout(_showBanner, 800);  // pequeño delay para que se vea el resultado primero
      }
    },
    reset() { _write({ n: 0, dismissed: false, last_seen: 0 }); },
  };
})();
