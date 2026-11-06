# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_compra.py
#  Lista de la compra
# ══════════════════════════════════════════════════════════════

from conftest import crear_usuario, entrar
from extensions import db
from models import ItemCompra


def _anadir(cliente, nombre="Leche", cantidad=""):
    return cliente.post(
        "/compra/nuevo", data={"nombre": nombre, "cantidad": cantidad}, follow_redirects=True
    )


def test_compra_pide_sesion(cliente):
    assert cliente.get("/compra/").status_code == 302


def test_lista_vacia(cliente_con_sesion):
    assert "La lista está vacía" in cliente_con_sesion.get("/compra/").get_data(as_text=True)


def test_anadir_producto(cliente_con_sesion):
    texto = _anadir(cliente_con_sesion, "Leche", "2 litros").get_data(as_text=True)
    item = ItemCompra.query.one()
    assert (item.nombre, item.cantidad, item.comprado) == ("Leche", "2 litros", False)
    assert "Leche" in texto and "2 litros" in texto


def test_nombre_obligatorio(cliente_con_sesion):
    respuesta = _anadir(cliente_con_sesion, "  ")
    assert respuesta.status_code == 400
    assert "Escribe qué hay que comprar" in respuesta.get_data(as_text=True)


def test_marcar_y_vaciar_comprados(cliente_con_sesion):
    _anadir(cliente_con_sesion, "Pan")
    _anadir(cliente_con_sesion, "Fruta")
    pan = ItemCompra.query.filter_by(nombre="Pan").one()

    texto = cliente_con_sesion.post(f"/compra/{pan.id}/marcar", follow_redirects=True).get_data(as_text=True)
    assert "En el carro" in texto
    db.session.refresh(pan)
    assert pan.comprado

    cliente_con_sesion.post("/compra/vaciar-comprados")
    assert [i.nombre for i in ItemCompra.query.all()] == ["Fruta"]


def test_borrar_producto(cliente_con_sesion):
    _anadir(cliente_con_sesion)
    item = ItemCompra.query.one()
    cliente_con_sesion.post(f"/compra/{item.id}/borrar")
    assert ItemCompra.query.count() == 0


def test_no_se_tocan_listas_ajenas(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = ItemCompra(usuario=otra, nombre="Chocolate secreto", comprado=True)
    db.session.add(ajeno)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Chocolate" not in cliente.get("/compra/").get_data(as_text=True)
    assert cliente.post(f"/compra/{ajeno.id}/marcar").status_code == 404
    assert cliente.post(f"/compra/{ajeno.id}/borrar").status_code == 404
    cliente.post("/compra/vaciar-comprados")            # no debe borrar lo de otra persona
    assert db.session.get(ItemCompra, ajeno.id) is not None


# ── Lista compacta, pasillos, productos preparados y frecuentes ──

from compra import pasillo_de, separar_cantidad
from models import ProductoFrecuente


def test_adivina_el_pasillo():
    assert pasillo_de("Leche") == "🥛 Lácteos y huevos"
    assert pasillo_de("leche entera") == "🥛 Lácteos y huevos"
    assert pasillo_de("Platanos") == "🥦 Fruta y verdura"          # sin tilde
    assert pasillo_de("tomate") == "🥦 Fruta y verdura"            # singular
    assert pasillo_de("Regalo de cumpleaños") == "🛒 Otros"


def test_separa_la_cantidad():
    assert separar_cantidad("2 leches") == ("Leches", "2")
    assert separar_cantidad("1 kg de patatas") == ("Patatas", "1 kg")
    assert separar_cantidad("500 g queso") == ("Queso", "500 g")
    assert separar_cantidad("pan") == ("Pan", None)


def test_cantidad_escrita_delante(cliente_con_sesion):
    _anadir(cliente_con_sesion, "2 litros de leche")
    item = ItemCompra.query.one()
    assert (item.nombre, item.cantidad) == ("Leche", "2 litros")


def test_lista_por_pasillos(cliente_con_sesion):
    for producto in ("Detergente", "Plátanos", "Leche"):
        _anadir(cliente_con_sesion, producto)
    texto = cliente_con_sesion.get("/compra/").get_data(as_text=True)
    lista = texto.split('aria-label="Por comprar"')[1].split("Añadir con un toque")[0]
    # En el orden del súper: fruta, lácteos… limpieza
    assert lista.index("Fruta y verdura") < lista.index("Lácteos") < lista.index("Limpieza")


def test_no_se_repite_lo_que_ya_esta(cliente_con_sesion):
    _anadir(cliente_con_sesion, "Leche")
    _anadir(cliente_con_sesion, "leche ")
    assert ItemCompra.query.count() == 1
    texto = cliente_con_sesion.get("/compra/").get_data(as_text=True)
    assert "Leche (ya está en la lista)" in texto                  # el botón del catálogo, marcado


def test_varios_de_golpe_por_voz(cliente_con_sesion):
    texto = cliente_con_sesion.post(
        "/compra/nuevo", data={"varios": "leche\npan\n2 kg patatas\n\nleche"}, follow_redirects=True
    ).get_data(as_text=True)
    assert sorted(i.nombre for i in ItemCompra.query) == ["Leche", "Pan", "Patatas"]
    assert "Añadidos 3 productos" in texto


def test_lo_que_sueles_comprar(cliente_con_sesion):
    for _ in range(3):
        _anadir(cliente_con_sesion, "Kéfir")
        cliente_con_sesion.post(f"/compra/{ItemCompra.query.one().id}/borrar")
    frecuente = ProductoFrecuente.query.one()
    assert (frecuente.nombre, frecuente.veces) == ("Kéfir", 3)
    texto = cliente_con_sesion.get("/compra/").get_data(as_text=True)
    assert "Lo que sueles comprar" in texto and "Kéfir" in texto

    cliente_con_sesion.post(f"/compra/frecuentes/{frecuente.id}/olvidar")
    assert ProductoFrecuente.query.count() == 0


def test_no_se_olvidan_frecuentes_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = ProductoFrecuente(usuario=otra, clave="secreto", nombre="Secreto")
    db.session.add(ajeno)
    db.session.commit()
    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)
    assert "Secreto" not in cliente.get("/compra/").get_data(as_text=True)
    assert cliente.post(f"/compra/frecuentes/{ajeno.id}/olvidar").status_code == 404
