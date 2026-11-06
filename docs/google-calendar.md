# Conectar Google Calendar: cómo conseguir las claves

Google solo deja que una app use tu calendario si la app tiene sus
propias claves (un «ID de cliente» y un «secreto»). Se crean gratis en
Google Cloud. Tardas unos 10 minutos y solo hay que hacerlo una vez.

> Las pantallas de Google cambian de vez en cuando. Si algún botón no
> se llama exactamente igual, busca el más parecido o pregúntame.

## 1. Crear el proyecto

1. Entra en <https://console.cloud.google.com/> con tu cuenta de Google.
   La primera vez te pedirá aceptar las condiciones de Google Cloud.
2. Arriba a la izquierda, junto al logo, pulsa el **selector de proyectos**
   y luego **Proyecto nuevo**.
3. Nombre: `Niebla mental` (o el nombre final de la app). Pulsa **Crear**.
4. Comprueba que arriba aparece seleccionado el proyecto nuevo.

## 2. Activar la API de Google Calendar

1. Menú ☰ → **APIs y servicios** → **Biblioteca**.
2. Busca **Google Calendar API**, ábrela y pulsa **Habilitar**.

## 3. Pantalla de consentimiento (lo que verás al conectar)

1. Menú ☰ → **APIs y servicios** → **Pantalla de consentimiento de OAuth**
   (puede aparecer como **Google Auth Platform**). Pulsa **Comenzar**.
2. **Información de la app**: nombre `Niebla mental` y tu email de asistencia.
3. **Público** (o «Audiencia»): elige **Externo**.
4. **Información de contacto**: tu email. Acepta la política y pulsa **Crear**.
5. En **Público**, debajo de **Usuarios de prueba**, pulsa **Añadir usuarios**
   y escribe **tu Gmail** (el del calendario que quieres conectar).
   Mientras la app esté «en prueba», solo esos emails pueden conectarse.

## 4. Crear las claves

1. Ve a **Clientes** (o **APIs y servicios** → **Credenciales** →
   **Crear credenciales** → **ID de cliente de OAuth**).
2. Tipo de aplicación: **Aplicación web**. Nombre: `Niebla mental (desarrollo)`.
3. En **URIs de redireccionamiento autorizados** añade estas dos:
   - `http://127.0.0.1:5050/google/vuelta`
   - `http://localhost:5050/google/vuelta`
4. Pulsa **Crear**. Aparecen el **ID de cliente** y el **Secreto del cliente**.

## 5. Ponerlas en la app

1. Abre el archivo `.env` del proyecto en PyCharm (no lo compartas con nadie).
2. Rellena estas dos líneas, que ya están al final del archivo:
   ```
   GOOGLE_CLIENT_ID=lo-que-termina-en.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=el-secreto
   ```
3. Guarda y **reinicia la app** (para el servidor y vuelve a arrancarlo):
   el `.env` solo se lee al arrancar.

## 6. Conectar

1. En la app, ve a **Agenda**. Aparece el panel **🔗 Google Calendar**.
2. Pulsa **Conectar con Google Calendar** y elige tu cuenta.
3. Google avisará de que **«Google no ha verificado esta aplicación»**.
   Es normal: la app es tuya y está en modo prueba. Pulsa
   **Continuar**.
4. Marca la casilla de **ver y editar eventos** del calendario y acepta.

Listo: lo de la app aparecerá en Google y lo de Google (próximos 60
días) en la app. Se sincroniza solo al abrir la agenda (como mucho cada
15 minutos) y también con el botón **🔄 Sincronizar ahora**.

## Cosas a saber

- **Privacidad de las citas médicas**: por defecto llegan a Google solo
  como «🩺 Cita médica» y la hora. Las preguntas y el resumen de la
  cita no salen nunca de la app. Puedes cambiarlo en el panel de la agenda.
- **En modo prueba, el permiso caduca a los 7 días**: es una regla de
  Google para apps sin verificar. Cuando pase, la app te avisará y
  solo tendrás que pulsar **Conectar** otra vez.
- **Para vender la app** (fase 8) habrá que:
  1. Añadir la dirección real: `https://tudominio/google/vuelta`.
  2. Pasar la **verificación de Google**: el permiso del calendario es
     «sensible», así que Google revisa la app, la política de
     privacidad y el dominio. Tarda unas semanas y es gratis.
  3. Publicar la app (salir del modo prueba).
