// ══════════════════════════════════════════════════════════════
//  App de organización · static/js/avisos.js
//  Recordatorios de medicación en el navegador.
//
//  De momento avisan mientras la app está abierta (en una pestaña
//  del PC o en el navegador del móvil). Cuando sea una PWA (fase 7)
//  llegarán también con la app cerrada, mediante notificaciones push.
// ══════════════════════════════════════════════════════════════

(() => {
  if (!("Notification" in window)) return;   // navegador sin notificaciones

  const URL_AVISOS = document.currentScript.dataset.url;
  const CLAVE_GUARDADO = "avisos-mostrados";
  const CADA = 60 * 1000;                     // comprobar cada minuto

  // ── Panel de la página de medicación ────────────────────────
  const panel = document.getElementById("panel-avisos");
  const estado = document.getElementById("estado-avisos");
  const botonActivar = document.getElementById("activar-avisos");

  function pintarPanel() {
    if (!panel) return;
    panel.hidden = false;
    const permiso = Notification.permission;
    botonActivar.hidden = permiso !== "default";
    if (permiso === "granted") {
      estado.textContent = "✓ Activados en este dispositivo. Te aviso a la hora de cada toma "
        + "mientras la app esté abierta.";
    } else if (permiso === "denied") {
      estado.textContent = "El navegador tiene bloqueadas las notificaciones de esta web. "
        + "Puedes permitirlas en los ajustes del sitio (el candado junto a la dirección).";
    } else {
      estado.textContent = "Te puedo avisar a la hora de cada toma mientras tengas la app abierta.";
    }
  }

  botonActivar?.addEventListener("click", async () => {
    await Notification.requestPermission();
    pintarPanel();
    comprobar();
  });

  // ── Comprobar si toca algo ──────────────────────────────────
  function yaMostrados() {
    try { return JSON.parse(localStorage.getItem(CLAVE_GUARDADO)) || []; }
    catch { return []; }
  }

  async function comprobar() {
    if (Notification.permission !== "granted") return;
    let datos;
    try {
      const respuesta = await fetch(URL_AVISOS, { headers: { Accept: "application/json" } });
      if (!respuesta.ok) return;
      datos = await respuesta.json();
    } catch { return; }                         // sin conexión: se reintenta luego

    // Solo se recuerdan los últimos, para no llenar el almacenamiento
    const mostrados = yaMostrados().slice(-50);

    for (const aviso of datos.avisos) {
      if (mostrados.includes(aviso.clave)) continue;
      try {
        const n = new Notification(aviso.titulo, { body: aviso.texto, tag: aviso.clave });
        n.onclick = () => { window.focus(); location.href = "/salud/medicacion/"; };
      } catch {
        // Chrome en Android solo permite avisos desde la PWA (fase 7)
        return;
      }
      mostrados.push(aviso.clave);
    }
    localStorage.setItem(CLAVE_GUARDADO, JSON.stringify(mostrados));
  }

  pintarPanel();
  comprobar();
  setInterval(comprobar, CADA);
})();
