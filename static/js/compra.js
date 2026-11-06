// ══════════════════════════════════════════════════════════════
//  App de organización · static/js/compra.js
//  Lista de la compra: dictar por voz y escanear códigos de barras.
//
//  Los dos botones solo aparecen si el navegador los admite:
//  - Voz: Chrome y Edge (en PC y Android) y Safari en iPhone.
//    Ojo: Chrome envía el audio a Google para pasarlo a texto.
//  - Escáner: Chrome en Android (necesita cámara y una web segura,
//    https). El nombre del producto se busca en Open Food Facts,
//    una base de datos libre de alimentos; solo se envía el código.
// ══════════════════════════════════════════════════════════════

(() => {
  const form = document.getElementById("form-compra");
  if (!form) return;
  const entrada = form.querySelector('input[name="nombre"]');
  const varios = document.getElementById("compra-varios");
  const estado = document.getElementById("compra-estado");
  const decir = (texto) => { estado.textContent = texto; };

  // ── Voz ─────────────────────────────────────────────────────
  // «Leche, pan y dos kilos de patatas» → tres productos
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const botonVoz = document.getElementById("boton-voz");

  function trocear(frase) {
    return frase
      .split(/\s*(?:,|;|\.|\by\b|\be\b|\bluego\b|\btambién\b)\s*/i)
      .map((t) => t.trim())
      .filter(Boolean);
  }

  if (Reconocimiento && botonVoz) {
    botonVoz.hidden = false;
    let escuchando = null;

    botonVoz.addEventListener("click", () => {
      if (escuchando) { escuchando.stop(); return; }
      const rec = new Reconocimiento();
      rec.lang = "es-ES";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      escuchando = rec;
      botonVoz.classList.add("escuchando");
      botonVoz.setAttribute("aria-label", "Dejar de escuchar");
      decir("Te escucho… di los productos, por ejemplo «leche, pan y huevos».");

      rec.onresult = (evento) => {
        const frase = evento.results[0][0].transcript;
        const productos = trocear(frase);
        if (!productos.length) { decir("No te he entendido. Prueba otra vez."); return; }
        decir(`He entendido: ${productos.join(", ")}`);
        varios.value = productos.join("\n");
        form.submit();
      };
      rec.onerror = (evento) => {
        decir(evento.error === "not-allowed"
          ? "El navegador no deja usar el micrófono. Permítelo en el candado junto a la dirección."
          : "No te he oído bien. Prueba otra vez.");
      };
      rec.onend = () => {
        escuchando = null;
        botonVoz.classList.remove("escuchando");
        botonVoz.setAttribute("aria-label", "Dictar por voz");
      };
      rec.start();
    });
  }

  // ── Escáner de códigos de barras ────────────────────────────
  const botonEscanear = document.getElementById("boton-escanear");
  const capa = document.getElementById("escaner");
  const video = document.getElementById("escaner-video");
  const cerrar = document.getElementById("escaner-cerrar");

  if ("BarcodeDetector" in window && navigator.mediaDevices?.getUserMedia && window.isSecureContext) {
    botonEscanear.hidden = false;
    let flujo = null;
    let buscando = false;

    function parar() {
      buscando = false;
      flujo?.getTracks().forEach((pista) => pista.stop());
      flujo = null;
      capa.hidden = true;
    }
    cerrar.addEventListener("click", parar);

    async function nombreDelProducto(codigo) {
      try {
        const url = `https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(codigo)}.json`
          + "?fields=product_name_es,product_name,generic_name_es";
        const respuesta = await fetch(url);
        if (!respuesta.ok) return null;
        const datos = await respuesta.json();
        const p = datos.product || {};
        return p.product_name_es || p.generic_name_es || p.product_name || null;
      } catch { return null; }
    }

    botonEscanear.addEventListener("click", async () => {
      let detector;
      try {
        detector = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
        flujo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      } catch {
        decir("No puedo usar la cámara. Revisa el permiso en el candado junto a la dirección.");
        return;
      }
      capa.hidden = false;
      video.srcObject = flujo;
      await video.play();
      buscando = true;

      while (buscando) {
        try {
          const codigos = await detector.detect(video);
          if (codigos.length) {
            const codigo = codigos[0].rawValue;
            parar();
            navigator.vibrate?.(80);
            decir("Buscando el producto…");
            const nombre = await nombreDelProducto(codigo);
            if (nombre) {
              entrada.value = nombre;
              decir(`Encontrado: «${nombre}». Pulsa ＋ para añadirlo (o cámbialo antes).`);
            } else {
              decir("No encuentro ese producto. Escribe el nombre tú.");
            }
            entrada.focus();
            break;
          }
        } catch { /* fotograma sin código: seguir mirando */ }
        await new Promise((r) => setTimeout(r, 250));
      }
    });
  }
})();
