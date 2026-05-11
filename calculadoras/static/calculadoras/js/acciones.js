/* acciones.js — Lógica compartida del modal de descarga/envío.
 *
 * Cada calc registra una función Alpine con Alpine.data() y la mezcla:
 *
 *   Alpine.data('ivaCalc', () => Object.assign(
 *     accionesMixin(),
 *     { modo: 'neto_a_bruto', monto: null, ... }
 *   ));
 *
 * Provee:  ultimoResultado, modalAbierto, accion, abrirModal, enviar,
 *          capturarResultado
 */
window.accionesMixin = function () {
  return {
    ultimoResultado: null,
    modalAbierto: false,
    accion: 'descargar',

    abrirModal(accion) {
      this.accion = accion;
      this.modalAbierto = true;
      this.renderTurnstile();
    },

    // Recibe el detalle del evento "resultado-listo" disparado por cada partial.
    capturarResultado(detail) {
      if (detail && typeof detail === "object") {
        this.ultimoResultado = detail;
      }
    },

    // Renderiza Turnstile manualmente cuando el modal se abre.
    // Cloudflare auto-renderiza al cargar la página, pero si el widget está
    // dentro de un x-show oculto inicialmente, no lo detecta.
    renderTurnstile() {
      this.$nextTick(() => {
        if (!window.turnstile) return;
        const el = this.$root.querySelector('.cf-turnstile');
        if (!el || el.dataset.rendered === 'true') return;
        try {
          window.turnstile.render(el, {
            sitekey: el.dataset.sitekey,
            size: el.dataset.size || 'flexible',
          });
          el.dataset.rendered = 'true';
        } catch (e) { /* widget may auto-init */ }
      });
    },

    async enviar(ev) {
      ev.preventDefault();
      const form = ev.target;
      const formData = new FormData(form);
      try {
        const resp = await fetch(form.action, { method: 'POST', body: formData });
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('application/pdf')) {
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          const disp = resp.headers.get('content-disposition') || '';
          const m = disp.match(/filename="([^"]+)"/);
          a.href = url; a.download = m ? m[1] : 'calculo.pdf';
          a.click();
          URL.revokeObjectURL(url);
          this.modalAbierto = false;
        } else {
          const data = await resp.json().catch(() => ({}));
          if (data.ok) {
            alert('✓ Enviado a tu correo.');
            this.modalAbierto = false;
          } else if (resp.status === 429) {
            alert('Has hecho demasiadas solicitudes. Intenta en unos minutos.');
          } else {
            alert('No se pudo procesar tu solicitud. Recarga e intenta de nuevo.');
          }
        }
      } catch {
        alert('Error de red. Intenta nuevamente.');
      }
    },
  };
};
