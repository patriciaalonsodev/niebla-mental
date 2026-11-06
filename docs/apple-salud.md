# Conectar Apple Salud (iPhone + Apple Watch) o Android

La guía completa, con tu dirección ya puesta, está dentro de la app:
**Perfil → ⌚ Reloj y Apple Salud → ver la guía paso a paso** (`/perfil/reloj/guia`).

## Resumen técnico

- Entrada: `POST /api/salud` con la cabecera `Authorization: Bearer <clave>`.
  La clave se crea en el Perfil; solo se guarda su huella SHA-256.
- Cuerpo JSON (todo opcional):

```json
{
  "fecha": "2026-11-06",
  "pasos": 8345, "minutos_activos": 34, "kcal_activas": 320, "distancia_km": 5.2,
  "ejercicios": [{"tipo": "Paseo", "minutos": 30, "kcal": 120}],
  "sueno": {"fecha": "2026-11-06", "acostarse": "2026-11-05T23:40:00+01:00",
            "levantarse": "2026-11-06T07:12:00+01:00", "profundo": 60, "rem": 90, "ligero": 250}
}
```

- Acepta números con coma o punto («7,5», «8.345») porque Atajos los manda según el idioma.
- Respuesta: `{"ok": true, "mensaje": "Guardado: 8345 pasos ✓"}` (para mostrarla como notificación).
- El iPhone tiene que poder llegar al servidor: funcionará cuando la app esté publicada con https.
