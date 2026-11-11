/* Progressive enhancement: forms remain usable without JavaScript. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const money = value => '$' + Math.round(Number(value || 0)).toLocaleString('es-CO');
  document.documentElement.classList.add('js-enabled');
  const header = $('.site-header');
  $('.nav-toggle')?.addEventListener('click', event => {
    const expanded = header.classList.toggle('menu-open');
    event.currentTarget.setAttribute('aria-expanded', String(expanded));
  });
  $$('.nav-links a').forEach(link => {
    const url = new URL(link.href);
    if (!url.hash && url.pathname === location.pathname) link.setAttribute('aria-current', 'page');
  });
  const spotlight = $('.hero-visual');
  const canTrack = matchMedia('(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)');
  spotlight?.addEventListener('pointermove', event => {
    if (!canTrack.matches || event.pointerType === 'touch') return;
    const bounds = spotlight.getBoundingClientRect();
    spotlight.style.setProperty('--spot-x', `${event.clientX - bounds.left}px`);
    spotlight.style.setProperty('--spot-y', `${event.clientY - bounds.top}px`);
  });
  let toastTimer;
  function toast(message, error = false, cartLink = false) {
    const region = $('#toast-region');
    if (!region) return;
    clearTimeout(toastTimer);
    region.replaceChildren();
    const box = document.createElement('div');
    box.className = 'toast' + (error ? ' error' : '');
    const text = document.createElement('span');
    text.textContent = message;
    box.append(text);
    if (cartLink) {
      const link = document.createElement('a');
      link.href = document.body.dataset.cartPage || '/carrito/';
      link.textContent = 'Ver carrito →';
      box.append(link);
    }
    const close = document.createElement('button');
    close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', 'Cerrar mensaje');
    close.addEventListener('click', () => region.replaceChildren());
    box.append(close); region.append(box);
    toastTimer = setTimeout(() => region.replaceChildren(), error ? 10000 : 6000);
  }
  const savedMessage = sessionStorage.getItem('carfit-message');
  if (savedMessage) { toast(savedMessage); sessionStorage.removeItem('carfit-message'); }

  // Password visibility never changes the value or sends a request.
  $$('input[type=password]').forEach(input => {
    const wrap = document.createElement('div'); wrap.className = 'password-wrap';
    input.before(wrap); wrap.append(input);
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'password-toggle';
    toggle.textContent = 'Mostrar'; toggle.setAttribute('aria-label', 'Mostrar ' + ($(`label[for="${input.id}"]`)?.textContent || 'contraseña'));
    toggle.setAttribute('aria-pressed', 'false');
    toggle.addEventListener('click', () => {
      const show = input.type === 'password'; input.type = show ? 'text' : 'password';
      toggle.textContent = show ? 'Ocultar' : 'Mostrar'; toggle.setAttribute('aria-pressed', String(show));
    });
    wrap.append(toggle);
  });
  $$('table.tabla').forEach(table => {
    const scroll = document.createElement('div'); scroll.className = 'table-scroll';
    scroll.tabIndex = 0; scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', 'Tabla desplazable');
    table.before(scroll); scroll.append(table);
  });

  // Only hide wizard panels once controls and validation have been installed.
  $$('[data-wizard]').forEach(form => {
    const panels = $$('[data-step-panel]', form);
    const indicators = $$('[data-step-indicator]', form);
    const next = $('[data-step-next]', form), back = $('[data-step-back]', form), submit = $('[type=submit]', form);
    let step = Math.max(0, panels.findIndex(panel => $('.errorlist', panel)));
    function showStep(index, focus = true) {
      step = index;
      panels.forEach((panel, i) => { panel.hidden = i !== step; });
      indicators.forEach((item, i) => {
        item.classList.toggle('is-active', i === step); item.classList.toggle('is-complete', i < step);
        if (i === step) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
      });
      back.hidden = step === 0; next.hidden = step === panels.length - 1; submit.hidden = step !== panels.length - 1;
      if (focus) { const legend = $('legend', panels[step]); legend.tabIndex = -1; legend.focus(); }
    }
    function valid(panel) {
      const invalid = $$('input,select,textarea', panel).find(input => !input.checkValidity());
      if (invalid) { invalid.reportValidity(); return false; }
      return true;
    }
    next.addEventListener('click', () => { if (valid(panels[step])) showStep(step + 1); });
    back.addEventListener('click', () => showStep(step - 1));
    form.addEventListener('submit', event => {
      if (step < panels.length - 1) { event.preventDefault(); if (valid(panels[step])) showStep(step + 1); return; }
      for (let i = 0; i < panels.length; i++) {
        const invalid = $$('input,select,textarea', panels[i]).find(input => !input.checkValidity());
        if (invalid) { event.preventDefault(); showStep(i, false); invalid.reportValidity(); return; }
      }
    });
    form.classList.add('wizard-ready'); showStep(step, false);
  });

  const catalog = $('[data-catalog]');
  if (catalog) {
    const cards = $$('[data-product]', catalog);
    const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    function filter() {
      const query = normalize($('#catalog-search').value.trim());
      const type = $('#catalog-type').value, state = $('#catalog-state').value;
      const order = $('#catalog-sort').value;
      let count = 0;
      cards.forEach(card => {
        const visible = (!query || normalize(card.dataset.search).includes(query)) &&
          (!type || type === card.dataset.type) && (!state || state === card.dataset.state);
        card.hidden = !visible; if (visible) count++;
      });
      $$('[data-product-grid]', catalog).forEach(grid => {
        const items = $$('[data-product]', grid);
        items.sort((a, b) => order === 'price-up' ? Number(a.dataset.price) - Number(b.dataset.price) :
          order === 'price-down' ? Number(b.dataset.price) - Number(a.dataset.price) : Number(a.dataset.index) - Number(b.dataset.index));
        items.forEach(card => grid.append(card));
        grid.closest('[data-catalog-section]').hidden = !items.some(card => !card.hidden);
      });
      $('[data-result-count]').textContent = count + (count === 1 ? ' artículo disponible' : ' artículos disponibles');
      $('[data-no-results]').hidden = count !== 0;
    }
    $$('#catalog-search,#catalog-type,#catalog-state,#catalog-sort').forEach(input => input.addEventListener('input', filter));
    $$('[data-filter-reset]').forEach(button => button.addEventListener('click', () => {
      $('#catalog-search').value = ''; $('#catalog-type').value = ''; $('#catalog-state').value = ''; filter();
    }));
    const category = new URLSearchParams(location.search).get('tipo');
    if (['carro','repuesto'].includes(category)) $('#catalog-type').value = category;
    filter();
  }

  function csrf() {
    return $('meta[name=csrf-token]')?.content || $('input[name=csrfmiddlewaretoken]')?.value ||
      document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.slice(10) || '';
  }
  function paintCart(cart) {
    $$('[data-cart-count]').forEach(el => { el.textContent = cart.cantidad_producto; });
  }
  let cartBusy = false;
  async function move(url, button) {
    if (cartBusy) return;
    cartBusy = true;
    const original = button?.textContent;
    if (button) { button.disabled = true; button.textContent = 'Actualizando…'; button.setAttribute('aria-busy','true'); }
    try {
      const response = await fetch(url, {method:'POST', headers:{Accept:'application/json', 'X-CSRFToken':csrf()}});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || response.redirected) throw new Error(data.detail || data.error || 'No se pudo actualizar. Revisa tu sesión e inténtalo de nuevo.');
      const action = (data.articulo || data).accion;
      const added = action === 'agregado';
      const message = added ? 'Artículo agregado al carrito.' : 'Carrito actualizado.';
      if ($('[data-checkout-page]')) {
        sessionStorage.setItem('carfit-message', message); location.reload(); return;
      }
      if (data.carrito) paintCart(data.carrito);
      if (button?.hasAttribute('data-carrito-toggle')) {
        const wasAdded = button.dataset.estado === 'dentro';
        if (!data.carrito && wasAdded !== added) {
          const currentCount = Number($('[data-cart-count]')?.textContent || 0);
          paintCart({cantidad_producto: Math.max(0, currentCount + (added ? 1 : -1))});
        }
        button.dataset.estado = added ? 'dentro' : 'fuera';
        button.dataset.url = added ? button.dataset.quitarUrl : button.dataset.agregarUrl;
        button.textContent = added ? '✓ En tu carrito · Quitar' : 'Agregar al carrito +';
        button.setAttribute('aria-pressed', String(added));
      } else if (button) button.textContent = original;
      toast(message, false, added);
    } catch (error) {
      if (button) button.textContent = original;
      toast(error.message || 'No hay conexión. Inténtalo de nuevo.', true);
    } finally {
      cartBusy = false;
      if (button) { button.disabled = false; button.removeAttribute('aria-busy'); }
    }
  }
  $$('[data-carrito-toggle],[data-cart-action]').forEach(button => {
    button.removeAttribute('onclick');
    button.addEventListener('click', () => {
      if (button.dataset.confirm && !window.confirm(button.dataset.confirm)) return;
      move(button.dataset.url, button);
    });
  });
  $('[data-logout]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const response = await fetch('/api/v2/logout/', {
        method:'POST', headers:{Accept:'application/json', 'X-CSRFToken':csrf()},
      });
      if (!response.ok) throw new Error('No se pudo cerrar la sesión. Inténtalo de nuevo.');
      location.assign('/');
    } catch (error) {
      toast(error.message, true); button.disabled = false;
    }
  });

  // One checkout preview for both rendering engines; per-item fees match the server.
  const checkout = $('[data-checkout]');
  if (checkout) {
    const prices = $$('[data-item-price]').map(el => Number(el.dataset.itemPrice));
    if (!prices.length) prices.push(Number(checkout.dataset.price || 0));
    function updatePayment() {
      const method = $('input[name=metodo_pago]:checked', checkout);
      if (!method) return;
      const required = (method.dataset.campos || '').split(',').filter(Boolean);
      $$('[data-campo]', checkout).forEach(wrap => {
        const name = wrap.dataset.campo;
        const visible = required.includes(name) || name === 'referencia' || (name === 'cuotas' && method.dataset.permiteCuotas === '1');
        wrap.hidden = !visible; wrap.style.display = visible ? '' : 'none';
        $$('input,select',wrap).forEach(input => {
          input.required = required.includes(name);
          input.disabled = !visible;
          if (name === 'cuotas') { input.max = method.dataset.cuotasMax || '1'; if (!visible) input.value = '1'; }
        });
      });
      const quotaWrap = $('[data-cuotas-wrap]',checkout);
      if (quotaWrap) {
        const allowed = method.dataset.permiteCuotas === '1'; quotaWrap.hidden = !allowed;
        const input = $('input', quotaWrap); input.max = method.dataset.cuotasMax || '1'; if (!allowed) input.value = '1';
      }
      const [whole, decimals = ''] = (method.dataset.comisionPct || '0').replace(',','.').split('.');
      const divisor = 10 ** decimals.length;
      const rate = Number(whole + decimals);
      const fixed = Number(method.dataset.comisionFija || 0);
      const fee = prices.reduce((sum, price) => sum + Math.floor((price * rate + divisor / 2) / divisor) + fixed, 0);
      const subtotal = prices.reduce((sum, price) => sum + price, 0);
      $('[data-resumen-comision]', checkout).textContent = money(fee);
      $('[data-resumen-total]', checkout).textContent = money(subtotal + fee);
    }
    $$('input[name=metodo_pago]', checkout).forEach(radio => radio.addEventListener('change', updatePayment));
    updatePayment();
  }
  $$('form').forEach(form => form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    // Keep server-side errors; add native feedback before sending incomplete fields.
    if (!form.checkValidity()) { event.preventDefault(); form.reportValidity(); return; }
    const submit = $('button[type=submit]', form);
    if (submit) {
      submit.dataset.originalLabel = submit.textContent;
      submit.disabled = true; submit.textContent = 'Procesando…'; submit.setAttribute('aria-busy','true');
    }
  }));
  window.addEventListener('pageshow', () => $$('button[type=submit][aria-busy]').forEach(button => {
    button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = button.dataset.originalLabel;
  }));
})();
