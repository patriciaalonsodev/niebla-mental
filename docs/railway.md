# Publicar la app en Railway (versión de prueba)

La app ya está preparada: Railway la detecta como app de Python, instala
`requirements.txt`, arranca con `gunicorn main:app` y, al arrancar, pone la
base de datos al día sola (migraciones). No hay que tocar comandos en Railway.

## 1. Subir el código a GitHub (privado)

1. Entra en <https://github.com/new>.
2. Nombre: `niebla-mental` (o el que quieras). Marca **Private**.
3. **No** añadas README, .gitignore ni licencia (el proyecto ya los tiene).
4. Pulsa **Create repository** y copia la dirección que termina en `.git`.
5. Pásamela y subo el código (`git push`). La primera vez se abrirá una
   ventana para que inicies sesión en GitHub.

## 2. Crear el servicio en Railway

1. En Railway → **New Project** (o dentro de un proyecto tuyo) →
   **Deploy from GitHub repo** → elige `niebla-mental`.
   La primera vez quizá tengas que dar permiso a Railway para ver ese repositorio.
2. Pulsa **+ New** (o **Create**) → **Database** → **PostgreSQL**.
3. Región: en la configuración de cada servicio (app y base de datos), elige
   una región de **Europa** (por ejemplo, EU West · Ámsterdam). Con datos de
   salud es lo que toca.

El primer intento de publicar fallará: aún no tiene las claves. Es normal.

## 3. Las variables (las claves)

En el servicio de la **app** → **Variables** → **Raw Editor**, pega el
contenido de `instance/claves-railway.txt` (desde `APP_CONFIG=` hasta el final).

- `DATABASE_URL=${{Postgres.DATABASE_URL}}` se escribe tal cual: Railway lo
  sustituye por la dirección de tu base de datos. Si tu base de datos tiene otro
  nombre en Railway, cambia `Postgres` por ese nombre.
- Opcionales: `APP_NOMBRE`, `ANTHROPIC_API_KEY` (recetas con IA),
  `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` (Google Calendar).

Al guardar, Railway vuelve a publicar la app.

## 4. La dirección web

App → **Settings** → **Networking** → **Generate Domain**. Te da algo como
`https://niebla-mental-production.up.railway.app`. Más adelante se puede
poner un dominio propio (p. ej. `app.patriciaalonso.es`).

Comprueba que funciona abriendo `https://TU-DIRECCION/estado`:
debe decir `{"estado": "ok"}`.

## 5. Después

- **Crea tu cuenta** en la nueva dirección: es una base de datos nueva, vacía
  (lo de tu PC se queda en tu PC).
- **Google Calendar**: en Google Cloud → Clientes → tu cliente → añade
  `https://TU-DIRECCION/google/vuelta` a los URIs de redireccionamiento.
- **Apple Watch**: en el Perfil de la app publicada, crea tu clave y sigue la guía.
- **Para tus conocidos**: diles que es una versión de prueba y que pueden usar
  datos inventados.

## Actualizar la app

Cada vez que guardemos cambios y hagamos `git push`, Railway publica la nueva
versión sola en un par de minutos.
