# App de organización (fibromialgia)

Flask + PostgreSQL · PWA (web + móvil)

## Puesta en marcha

1. Entorno virtual e instalación:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copia `.env.example` como `.env` y rellena:
   - `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL`: tu base de datos PostgreSQL (créala antes, vacía).
   - `CLAVE_CIFRADO_DATOS`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
     ⚠️ Haz copia de seguridad de esta clave. Sin ella, el diario no se puede recuperar.
3. Primera migración (crea las tablas):
   ```bash
   flask db migrate -m "usuarios y núcleo"
   flask db upgrade
   ```
   Revisa el archivo generado en `migrations/versions/` antes del `upgrade`.
4. Arrancar: `flask run` y abrir http://127.0.0.1:5050/estado → `{"estado": "ok"}`.

## Tests

```bash
pytest
```

## Nota sobre migraciones

`migrations/script.py.mako` incluye `import models`, porque Alembic escribe la
columna cifrada como `models.TextoCifrado()`. Sin ese import, la migración falla.

## Plan de fases

El nombre de la app es provisional: se cambia en `APP_NOMBRE` (config.py o .env).

1. ✅ **Base**: Flask, modelo de datos, cifrado, migraciones, diseño lavanda.
2. ✅ **Núcleo**
   - ✅ Cuentas: registro, inicio de sesión, consentimientos RGPD.
   - ✅ Tareas con coste de energía (cucharas).
   - ✅ Notas con etiquetas y buscador.
   - ✅ Lista de la compra.
   - ✅ Captura rápida («＋ Apuntar algo») con bandeja para ordenar en tarea, nota o compra.
3. ✅ **Salud**
   - ✅ Registro diario de síntomas (dolor, cansancio, sueño, niebla, rigidez, ánimo; escala 0–10) con historial de 14 días.
   - ✅ Medicación: horario del día, tomas (tomada, saltada, a demanda), pausar, aviso en el inicio y recordatorios del navegador con la app abierta (con la app cerrada llegarán en la fase 7, PWA).
   - ✅ Diario cifrado: ánimo, preguntas guía, etiquetas, buscador (sin tildes) y páginas.
4. 🔄 **Integraciones**
   - ✅ Agenda propia: eventos y citas médicas (profesional, preguntas para la consulta, resumen de lo que dijeron), con cucharas por día y resumen de hoy y mañana en el inicio.
   - ✅ Sincronizar con Google Calendar en los dos sentidos, con citas médicas privadas por defecto. Cómo crear las claves: [docs/google-calendar.md](docs/google-calendar.md).
   - ⬜ Apple Salud vía Atajos (sueño, pasos, ejercicio).
5. ✅ **Cuerpo y comida**
   - ✅ Nutrición: plan diario (calorías y macros con Mifflin-St Jeor, ajustable a mano), comidas del día con barras de lo que queda, mis alimentos (por 100 g), peso con gráfica y recetas con IA (Claude; necesita `ANTHROPIC_API_KEY`).
   - ✅ Actividad: pasos con objetivo y anillo, ejercicios, gráfica semanal.
   - ✅ Sueño: duración, fases, calidad y gráfica semanal.
   - ✅ Enlace con el reloj: entrada `POST /api/salud` con clave personal (Apple Salud vía Atajos; Android con cualquier app que lea Health Connect). Guía en la app y en [docs/apple-salud.md](docs/apple-salud.md).
6. ⬜ **Extras**: presupuesto diario de cucharas, modo día malo, informe PDF para el médico, voz.
7. ⬜ **PWA**: instalable en móvil y PC, notificaciones push, modo sin conexión.
8. ⬜ **Venta**: suscripción desde la web con Stripe; textos legales revisados.
