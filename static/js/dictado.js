// ══════════════════════════════════════════════════════════════
//  App de organización · static/js/dictado.js
//  Dictado por voz en todos los campos de texto de la app.
//
//  - Pone un botón 🎤 dentro de cada cuadro de texto. Al pulsarlo,
//    lo que dices se va escribiendo; al pulsarlo otra vez, para.
//  - En los cuadros grandes (diario, notas…) sigue escuchando hasta
//    que lo paras; en los pequeños (un título) para al callarte.
//  - Entiende órdenes: «punto», «coma», «dos puntos», «punto y aparte»,
//    «nueva línea», «abre interrogación»… y pone mayúscula al empezar.
//  - Funciona en Chrome, Edge y Safari (también en el iPhone).
//    Ojo: el navegador envía la voz a su servicio (Google o Apple)
//    para pasarla a texto.
//  - Un campo puede no tenerlo con data-sin-dictado.
// ══════════════════════════════════════════════════════════════

(() => {
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Reconocimiento) return;                 // navegador sin dictado: no se pone nada

  const SELECTOR = [
    "textarea",
    '.campo input[type="text"]',
    'input.hoja-campo-etiquetas',
  ].join(",");

  // ── Órdenes de puntuación ───────────────────────────────────
  // El orden importa: «punto y aparte» antes que «punto».
  const ORDENES = [
    [/\s*\b(punto y aparte|nuevo párrafo)\b\s*/gi, ".\n"],
    [/\s*\b(nueva línea|salto de línea)\b\s*/gi, "\n"],
    [/\s*\bpunto y coma\b\s*/gi, "; "],
    [/\s*\bdos puntos\b\s*/gi, ": "],
    [/\s*\bpuntos suspensivos\b\s*/gi, "… "],
    [/\s*\bpunto\b\s*/gi, ". "],
    [/\s*\bcoma\b\s*/gi, ", "],
    [/\s*\babre interrogación\b\s*/gi, " ¿"],
    [/\s*\bcierra interrogación\b\s*/gi, "? "],
    [/\s*\babre exclamación\b\s*/gi, " ¡"],
    [/\s*\bcierra exclamación\b\s*/gi, "! "],
  ];

  function aplicarOrdenes(texto) {
    let resultado = texto;
    for (const [patron, signo] of ORDENES) resultado = resultado.replace(patron, signo);
    return resultado.replace(/ +([.,;:!?…])/g, "$1").replace(/ {2,}/g, " ");
  }

  // Mayúscula al principio y después de . ? ! o de un salto de línea
  function mayusculas(texto, anterior) {
    const empiezaFrase = !anterior.trim() || /[.?!…]\s*$|\n\s*$/.test(anterior);
    // Tras «¿» o «¡» solo si empieza frase: «Tengo cita ¿mañana o el lunes?»
    let resultado = texto.replace(/([.?!…]\s+[¿¡]?|\n\s*[¿¡]?)([a-záéíóúñü])/g, (_, a, b) => a + b.toUpperCase());
    if (empiezaFrase) resultado = resultado.replace(/^(\s*[¿¡]?)([a-záéíóúñü])/, (_, a, b) => a + b.toUpperCase());
    return resultado;
  }

  // Une lo que ya había con lo nuevo, con el espacio justo
  function unir(anterior, nuevo) {
    if (!anterior) return nuevo.trimStart();
    if (/ $/.test(anterior)) return anterior + nuevo.replace(/^ +/, "");   // sin espacios dobles
    if (/[\s¿¡(]$/.test(anterior) || /^[\s.,;:!?…]/.test(nuevo)) return anterior + nuevo;
    return anterior + " " + nuevo;
  }

  // Avisar a la página de que el campo ha cambiado (contadores, etc.)
  function avisar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }

  let activo = null;                           // solo un micrófono a la vez

  function preparar(campo) {
    if (campo.dataset.dictadoListo || campo.closest("[data-sin-dictado]") || campo.hasAttribute("data-sin-dictado")) return;
    if (campo.readOnly || campo.disabled || campo.type === "hidden") return;
    campo.dataset.dictadoListo = "1";

    const largo = campo.tagName === "TEXTAREA";
    const envoltorio = document.createElement("span");
    envoltorio.className = "dictado" + (largo ? " dictado-largo" : "");
    campo.parentNode.insertBefore(envoltorio, campo);
    envoltorio.appendChild(campo);

    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "dictado-boton";
    boton.textContent = "🎤";
    const nombre = (campo.labels && campo.labels[0] && campo.labels[0].textContent.trim()) || "este campo";
    boton.setAttribute("aria-label", `Dictar por voz: ${nombre}`);
    boton.title = "Dictar por voz (el navegador convierte tu voz en texto)";
    envoltorio.appendChild(boton);

    boton.addEventListener("click", () => {
      if (activo && activo.campo === campo) { activo.rec.stop(); return; }
      if (activo) activo.rec.stop();

      const rec = new Reconocimiento();
      rec.lang = "es-ES";
      rec.interimResults = true;               // ver el texto mientras hablas
      rec.continuous = largo;
      let base = campo.value;
      activo = { rec, campo };
      boton.classList.add("escuchando");
      boton.textContent = "⏹";
      boton.setAttribute("aria-label", "Dejar de dictar");
      campo.classList.add("dictando");

      rec.onresult = (evento) => {
        let provisional = "";
        for (let i = evento.resultIndex; i < evento.results.length; i++) {
          const frase = evento.results[i][0].transcript;
          if (evento.results[i].isFinal) {
            const limpio = mayusculas(aplicarOrdenes(frase), base);
            base = unir(base, limpio);
          } else {
            provisional += frase;
          }
        }
        campo.value = provisional ? unir(base, mayusculas(aplicarOrdenes(provisional), base)) : base;
        if (largo) campo.scrollTop = campo.scrollHeight;
        avisar(campo);
      };
      rec.onerror = (evento) => {
        if (evento.error === "not-allowed" || evento.error === "service-not-allowed") {
          alert("El navegador no deja usar el micrófono. Permítelo en el candado junto a la dirección (o en Ajustes › Safari › Micrófono).");
        }
      };
      rec.onend = () => {
        base = base.replace(/ +$/, "");
        campo.value = base;
        avisar(campo);
        boton.classList.remove("escuchando");
        boton.textContent = "🎤";
        boton.setAttribute("aria-label", `Dictar por voz: ${nombre}`);
        campo.classList.remove("dictando");
        if (activo && activo.rec === rec) activo = null;
        campo.focus();
      };
      try { rec.start(); } catch { rec.onend(); }
    });
  }

  document.querySelectorAll(SELECTOR).forEach(preparar);

  // Si se va de la página mientras dicta, que pare
  window.addEventListener("pagehide", () => activo && activo.rec.abort());
})();
