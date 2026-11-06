# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_perfil.py
#  Perfil y barra de navegación
# ══════════════════════════════════════════════════════════════

from extensions import db
from models import Usuario


def test_perfil_pide_sesion(cliente):
    assert cliente.get("/perfil/").status_code == 302


def test_ver_perfil(cliente_con_sesion):
    texto = cliente_con_sesion.get("/perfil/").get_data(as_text=True)
    assert "patz@example.com" in texto and 'value="Patz"' in texto
    assert "Cerrar sesión" in texto and "Europe/Madrid" in texto


def test_cambiar_nombre_tema_y_zona(cliente_con_sesion):
    texto = cliente_con_sesion.post("/perfil/", data={
        "nombre": "Patricia", "tema": "claro", "zona_horaria": "America/Bogota",
    }, follow_redirects=True).get_data(as_text=True)
    usuario = db.session.scalar(db.select(Usuario))
    assert (usuario.nombre, usuario.tema, usuario.zona_horaria) == ("Patricia", "claro", "America/Bogota")
    assert 'data-tema="claro"' in texto and "Perfil guardado" in texto


def test_zona_horaria_inventada(cliente_con_sesion):
    respuesta = cliente_con_sesion.post("/perfil/", data={
        "nombre": "Patz", "tema": "oscuro", "zona_horaria": "Marte/Olympus",
    })
    assert respuesta.status_code == 400
    assert db.session.scalar(db.select(Usuario)).zona_horaria == "Europe/Madrid"


def test_barra_de_navegacion(cliente_con_sesion):
    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    for destino in ('href="/"', 'href="/eventos/"', 'href="/apuntar/"', 'href="/salud/"', 'href="/perfil/"'):
        assert destino in texto
    # Se ilumina la sección en la que estás
    assert 'nav-salud nav-activo' in cliente_con_sesion.get("/salud/medicacion/").get_data(as_text=True)
    assert 'nav-agenda nav-activo' in cliente_con_sesion.get("/eventos/").get_data(as_text=True)


def test_volver_al_inicio_desde_las_secciones(cliente_con_sesion):
    for ruta in ("/tareas/", "/notas/", "/compra/", "/diario/"):
        assert "← Inicio" in cliente_con_sesion.get(ruta).get_data(as_text=True)
    assert "← Inicio" not in cliente_con_sesion.get("/").get_data(as_text=True)


def test_sin_sesion_no_hay_barra(cliente):
    assert 'class="navegacion"' not in cliente.get("/entrar").get_data(as_text=True)


# ── Foto de perfil ────────────────────────────────────────────

from io import BytesIO

from PIL import Image


def _imagen(formato="PNG", tamano=(800, 600), color=(200, 180, 250)):
    datos = BytesIO()
    Image.new("RGB", tamano, color).save(datos, formato)
    datos.seek(0)
    return datos


def test_subir_foto(cliente_con_sesion):
    texto = cliente_con_sesion.post(
        "/perfil/foto", data={"foto": (_imagen(), "yo.png")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)
    usuario = db.session.scalar(db.select(Usuario))
    assert "Foto de perfil puesta" in texto and usuario.foto_version == 1
    with Image.open(BytesIO(usuario.foto)) as guardada:
        assert (guardada.format, guardada.size) == ("WEBP", (256, 256))   # recortada y reducida
    assert 'src="/perfil/foto?v=1"' in texto                              # también en la barra

    respuesta = cliente_con_sesion.get("/perfil/foto?v=1")
    assert respuesta.mimetype == "image/webp" and "private" in respuesta.headers["Cache-Control"]


def test_no_acepta_lo_que_no_es_imagen(cliente_con_sesion):
    texto = cliente_con_sesion.post(
        "/perfil/foto", data={"foto": (BytesIO(b"<script>malo</script>"), "foto.png")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)
    assert "No he podido leer esa imagen" in texto
    assert db.session.scalar(db.select(Usuario)).foto is None
    texto = cliente_con_sesion.post(
        "/perfil/foto", data={"foto": (BytesIO(b"hola"), "notas.txt")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)
    assert "Tiene que ser una foto" in texto


def test_quitar_foto(cliente_con_sesion):
    cliente_con_sesion.post("/perfil/foto", data={"foto": (_imagen("JPEG"), "yo.jpg")},
                            content_type="multipart/form-data")
    cliente_con_sesion.post("/perfil/foto/quitar")
    assert db.session.scalar(db.select(Usuario)).foto is None
    assert cliente_con_sesion.get("/perfil/foto").status_code == 404


def test_foto_demasiado_grande(cliente_con_sesion):
    enorme = BytesIO(b"0" * (9 * 1024 * 1024))
    texto = cliente_con_sesion.post(
        "/perfil/foto", data={"foto": (enorme, "enorme.jpg")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)
    assert "demasiado grande" in texto
