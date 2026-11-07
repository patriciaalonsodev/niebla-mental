from datetime import time

from extensions import db
from models import RegistroActividad, RegistroSueno, Tarea, Usuario


def test_inicio_con_el_dia_de_hoy(cliente_con_sesion):
    usuario = Usuario.query.one()
    hoy = usuario.hoy()
    cliente_con_sesion.post("/tareas/nueva", data={"titulo": "Llamar al médico", "fecha": hoy.isoformat(), "hora": "10:30"})
    tarea = Tarea.query.one()
    assert tarea.hora == time(10, 30)
    db.session.add(RegistroSueno(usuario_id=usuario.id, fecha=hoy, minutos_dormido=403,
                                 hora_acostarse=time(2, 27), hora_levantarse=time(9, 12), origen="reloj"))
    db.session.add(RegistroActividad(usuario_id=usuario.id, fecha=hoy, pasos=4321, origen="reloj"))
    db.session.commit()

    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    assert "Llamar al médico" in texto and "10:30" in texto
    assert "6 h 43 min" in texto and "02:27 – 09:12" in texto
    assert "4.321" in texto
    assert "img/iconos/inicio.png" in texto                     # la casa, no el logo, en la barra

    # Marcarla desde el inicio vuelve al inicio
    respuesta = cliente_con_sesion.post(f"/tareas/{tarea.id}/completar", data={"volver": "/"})
    assert respuesta.location == "/"
    assert "Todo hecho por hoy" in cliente_con_sesion.get("/").get_data(as_text=True)
