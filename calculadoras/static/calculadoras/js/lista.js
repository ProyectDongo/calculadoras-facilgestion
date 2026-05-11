/* lista.js — Helper para gestión de listas multi-ítem en localStorage.
 *
 * Storage key:  calc_lista_precio_venta
 * Schema:       { items: [{descripcion, cantidad, precio_unitario, fuente, _id, _ts}], emisor: {...} }
 *
 * Todo el estado vive en el navegador del usuario. El backend solo recibe el
 * snapshot al momento de exportar PDF.
 */
window.listaStore = (function () {
  const STORAGE_KEY = 'calc_lista_precio_venta';
  const EMISOR_KEY  = 'calc_emisor';

  function _read() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { items: [] };
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.items)) return { items: [] };
      return data;
    } catch { return { items: [] }; }
  }

  function _write(data) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }
    catch { /* quota / private mode — ignorar */ }
  }

  function _emisor() {
    try {
      const raw = localStorage.getItem(EMISOR_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  }

  function _setEmisor(em) {
    try { localStorage.setItem(EMISOR_KEY, JSON.stringify(em || {})); }
    catch { /* idem */ }
  }

  return {
    // Devuelve copia inmutable de los items
    list() { return _read().items.slice(); },

    count() { return _read().items.length; },

    add(item) {
      const data = _read();
      const enriched = {
        _id: Date.now() + ':' + Math.random().toString(36).slice(2, 7),
        _ts: Date.now(),
        descripcion: String(item.descripcion || '').slice(0, 200).trim() || 'Producto',
        cantidad: Math.max(1, parseInt(item.cantidad || 1, 10)),
        precio_unitario: Math.max(0, parseInt(item.precio_unitario || 0, 10)),
        fuente: item.fuente || 'precio_venta',
      };
      data.items.push(enriched);
      _write(data);
      window.dispatchEvent(new CustomEvent('lista-cambio', { detail: { count: data.items.length } }));
      return enriched;
    },

    remove(id) {
      const data = _read();
      data.items = data.items.filter(i => i._id !== id);
      _write(data);
      window.dispatchEvent(new CustomEvent('lista-cambio', { detail: { count: data.items.length } }));
    },

    updateQty(id, cantidad) {
      const data = _read();
      const it = data.items.find(i => i._id === id);
      if (it) {
        it.cantidad = Math.max(1, parseInt(cantidad, 10) || 1);
        _write(data);
        window.dispatchEvent(new CustomEvent('lista-cambio', { detail: { count: data.items.length } }));
      }
    },

    clear() {
      _write({ items: [] });
      window.dispatchEvent(new CustomEvent('lista-cambio', { detail: { count: 0 } }));
    },

    emisor: _emisor,
    setEmisor: _setEmisor,
  };
})();
