/* ══════════════════════════════════════════════════════════════
   App de organización · static/js/libro.js
   Pasar de página como una hoja de papel (diario y agenda).
   Basado en el libro.js de pz-verse.com, de Patz.

   La esquina inferior derecha se levanta, la hoja se dobla y se
   pasa hacia la izquierda, dejando ver la página siguiente debajo.
   Al ir hacia atrás (enlaces con class="pasar-atras" o el botón
   Atrás del navegador), la hoja se despliega de nuevo.

   Usa «View Transitions» entre páginas (Chrome, Edge y Safari
   recientes). Sin soporte, o con «reducir movimiento», se navega
   normal. Solo actúa entre páginas que cargan este archivo.
   ══════════════════════════════════════════════════════════════ */
(function () {
  // Colores del reverso del papel lila (de la grieta hacia el resto de la hoja)
  var PAPEL = { grieta: '#4a3a7a', brillo: '#f4eeff', medio: '#ddd0fa', fondo: '#c7b5f2' };
  var FRAMES = 64;
  var CLAVE_ATRAS = 'libro-atras';

  // Marcar las navegaciones «hacia atrás» antes de salir de la página
  document.addEventListener('click', function (e) {
    var enlace = e.target.closest && e.target.closest('a.pasar-atras');
    if (enlace) sessionStorage.setItem(CLAVE_ATRAS, '1');
  });

  /* ---------- geometría del doblez ---------- */
  function recortar(poli, g) {            // Sutherland–Hodgman: conserva g(P) >= 0
    var sal = [];
    for (var i = 0; i < poli.length; i++) {
      var a = poli[i], b = poli[(i + 1) % poli.length], ga = g(a), gb = g(b);
      if (ga >= 0) sal.push(a);
      if ((ga >= 0) !== (gb >= 0)) {
        var t = ga / (ga - gb);
        sal.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    return sal;
  }
  function css(poli) {
    if (poli.length < 3) return 'polygon(0px 0px,0px 0px,0px 0px)';
    return 'polygon(' + poli.map(function (p) { return p[0].toFixed(1) + 'px ' + p[1].toFixed(1) + 'px'; }).join(',') + ')';
  }

  // p: 0 = hoja plana · 1 = hoja pasada del todo
  function fotograma(p, W, H) {
    var rect = [[0, 0], [W, 0], [W, H], [0, H]];
    var cx = W, cy = H;                                   // esquina que se levanta
    var nx = W - p * 2 * W;                               // hacia dónde se arrastra…
    var ny = H - 0.34 * W * Math.sin(Math.PI * p);        // …levantándola en arco
    var dx = nx - cx, dy = ny - cy, dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 0.8) return { resto: css(rect), hoja: css([]), fondo: 'none', p: p };

    var ux = dx / dist, uy = dy / dist;                   // normal del doblez
    var mx = (cx + nx) / 2, my = (cy + ny) / 2;           // punto del doblez
    function f(P) { return (P[0] - mx) * ux + (P[1] - my) * uy; }

    var resto = recortar(rect, f);                        // parte que sigue plana
    var movil = recortar(rect, function (P) { return -f(P); });
    var hoja = movil.map(function (P) {                   // reflejo = reverso de la hoja
      var k = 2 * f(P);
      return [P[0] - k * ux, P[1] - k * uy];
    });
    hoja = recortar(hoja, function (P) { return P[0]; });
    hoja = recortar(hoja, function (P) { return W - P[0]; });
    hoja = recortar(hoja, function (P) { return P[1]; });
    hoja = recortar(hoja, function (P) { return H - P[1]; });

    // Degradado del reverso, perpendicular al doblez
    var ang = Math.atan2(ux, -uy) * 180 / Math.PI;
    var len = Math.abs(W * Math.sin(ang * Math.PI / 180)) + Math.abs(H * Math.cos(ang * Math.PI / 180));
    var sx = W / 2 - ux * len / 2, sy = H / 2 - uy * len / 2;
    var t0 = (mx - sx) * ux + (my - sy) * uy;
    var fondo = 'linear-gradient(' + ang.toFixed(2) + 'deg,' +
      PAPEL.grieta + ' ' + t0.toFixed(1) + 'px,' +
      PAPEL.brillo + ' ' + (t0 + 7).toFixed(1) + 'px,' +
      PAPEL.medio + ' ' + (t0 + 55).toFixed(1) + 'px,' +
      PAPEL.fondo + ' ' + (t0 + 520).toFixed(1) + 'px)';
    return { resto: css(resto), hoja: css(hoja), fondo: fondo, p: p };
  }

  function suave(t) {                                     // arranque lento, final rápido
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  /* ---------- la transición ---------- */
  window.addEventListener('pagereveal', function (e) {
    var vt = e.viewTransition;
    var atrasMarcado = sessionStorage.getItem(CLAVE_ATRAS) === '1';
    sessionStorage.removeItem(CLAVE_ATRAS);
    if (!vt) return;

    var raiz = document.documentElement;
    var W = raiz.clientWidth, H = raiz.clientHeight;
    var atras = atrasMarcado ||
      !!(window.navigation && navigation.activation && navigation.activation.navigationType === 'traverse');
    var dur = W <= 800 ? 800 : 1100;

    raiz.style.setProperty('--pasar-hoja', dur + 'ms');
    raiz.classList.add('libro-activo');
    if (atras) raiz.classList.add('libro-atras');

    var hoja = document.createElement('div');
    hoja.id = 'libro-hoja';
    var pliegue = document.createElement('div');
    pliegue.className = 'pliegue';
    pliegue.style.clipPath = css([]);
    hoja.appendChild(pliegue);
    raiz.appendChild(hoja);

    function limpiar() {
      raiz.classList.remove('libro-activo', 'libro-atras');
      raiz.style.removeProperty('--pasar-hoja');
      if (hoja.parentNode) hoja.parentNode.removeChild(hoja);
    }
    vt.finished.then(limpiar, limpiar);

    vt.ready.then(function () {
      var fr = [];
      for (var i = 0; i <= FRAMES; i++) {
        var t = i / FRAMES;
        fr.push(fotograma(suave(atras ? 1 - t : t), W, H));
      }
      var opc = { duration: dur, easing: 'linear', fill: 'both' };
      var encima = atras ? '::view-transition-new(root)' : '::view-transition-old(root)';
      var debajo = atras ? '::view-transition-old(root)' : '::view-transition-new(root)';

      raiz.animate(fr.map(function (k, i) { return { offset: i / FRAMES, clipPath: k.resto }; }),
        Object.assign({ pseudoElement: encima }, opc));
      raiz.animate(fr.map(function (k, i) { return { offset: i / FRAMES, filter: 'brightness(' + (0.55 + 0.45 * k.p).toFixed(3) + ')' }; }),
        Object.assign({ pseudoElement: debajo }, opc));
      pliegue.animate(fr.map(function (k, i) { return { offset: i / FRAMES, clipPath: k.hoja, backgroundImage: k.fondo }; }), opc);
    }).catch(limpiar);      // si el navegador se salta la transición (pestaña oculta, etc.)
  });
})();
