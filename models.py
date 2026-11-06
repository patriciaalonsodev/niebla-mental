# ══════════════════════════════════════════════════════════════
#  App de organización · models.py
#  Modelo de datos: usuarios y núcleo (tareas, notas, diario,
#  lista de la compra y etiquetas)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import os
from datetime import date, datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.types import Text, TypeDecorator
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def ahora_utc():
    """Fecha y hora actual en UTC. Se guarda todo en UTC y se
    convierte a la zona horaria del usuario al mostrarlo."""
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _fernet():
    """Devuelve el cifrador Fernet. Se crea una sola vez y solo
    cuando se necesita, así la app arranca aunque falte la clave
    en scripts que no tocan datos cifrados."""
    clave = os.environ.get("CLAVE_CIFRADO_DATOS")
    if not clave:
        raise RuntimeError(
            "Falta la variable de entorno CLAVE_CIFRADO_DATOS. "
            "Sin ella no se pueden leer ni guardar datos cifrados."
        )
    return Fernet(clave.encode())


class TextoCifrado(TypeDecorator):
    """Columna de texto que se cifra al guardar y se descifra al
    leer. En la base de datos solo se ve el texto cifrado."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


class MarcasTiempo:
    """Mixin: añade fecha de creación y de última edición."""

    creado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=ahora_utc
    )
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=ahora_utc,
        onupdate=ahora_utc,
    )


# ──────────────────────────────────────────────────────────────
# Tablas puente (etiquetas compartidas entre notas y diario)
# ──────────────────────────────────────────────────────────────

nota_etiquetas = db.Table(
    "nota_etiquetas",
    db.Column(
        "nota_id",
        db.Integer,
        db.ForeignKey("notas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "etiqueta_id",
        db.Integer,
        db.ForeignKey("etiquetas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

diario_etiquetas = db.Table(
    "diario_etiquetas",
    db.Column(
        "entrada_id",
        db.Integer,
        db.ForeignKey("entradas_diario.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "etiqueta_id",
        db.Integer,
        db.ForeignKey("etiquetas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ──────────────────────────────────────────────────────────────
# Usuarios
# ──────────────────────────────────────────────────────────────

class Usuario(UserMixin, MarcasTiempo, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    tema = db.Column(db.String(20), nullable=False, default="oscuro")
    zona_horaria = db.Column(
        db.String(50), nullable=False, default="Europe/Madrid"
    )

    # RGPD: cuándo aceptó la política de privacidad y cuándo dio su
    # consentimiento explícito para tratar datos de salud (art. 9).
    # Foto de perfil: pequeña (256×256, WebP) y guardada en la base de
    # datos, así no se pierde al cambiar de servidor.
    foto = db.Column(db.LargeBinary)
    foto_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    # Clave personal para que Apple Salud (Atajos) o Android envíen datos.
    # Solo se guarda su huella (SHA-256), nunca la clave en sí.
    api_token_hash = db.Column(db.String(64), unique=True, index=True)
    api_token_creado = db.Column(db.DateTime(timezone=True))
    objetivo_pasos = db.Column(db.Integer, nullable=False, default=6000, server_default="6000")

    privacidad_aceptada_en = db.Column(db.DateTime(timezone=True))
    consentimiento_salud_en = db.Column(db.DateTime(timezone=True))

    # cascade="all, delete-orphan": si se borra la cuenta, se borra
    # todo lo suyo (derecho de supresión del RGPD).
    tareas = db.relationship(
        "Tarea", back_populates="usuario", cascade="all, delete-orphan"
    )
    notas = db.relationship(
        "Nota", back_populates="usuario", cascade="all, delete-orphan"
    )
    entradas_diario = db.relationship(
        "EntradaDiario", back_populates="usuario", cascade="all, delete-orphan"
    )
    items_compra = db.relationship(
        "ItemCompra", back_populates="usuario", cascade="all, delete-orphan"
    )
    productos_frecuentes = db.relationship(
        "ProductoFrecuente", back_populates="usuario", cascade="all, delete-orphan"
    )
    plan_nutricion = db.relationship(
        "PlanNutricion", back_populates="usuario", cascade="all, delete-orphan", uselist=False
    )
    alimentos = db.relationship(
        "Alimento", back_populates="usuario", cascade="all, delete-orphan"
    )
    comidas = db.relationship(
        "Comida", back_populates="usuario", cascade="all, delete-orphan"
    )
    pesos = db.relationship(
        "RegistroPeso", back_populates="usuario", cascade="all, delete-orphan"
    )
    recetas = db.relationship(
        "RecetaGuardada", back_populates="usuario", cascade="all, delete-orphan"
    )
    usos_ia = db.relationship(
        "UsoIA", back_populates="usuario", cascade="all, delete-orphan"
    )
    actividades = db.relationship(
        "RegistroActividad", back_populates="usuario", cascade="all, delete-orphan"
    )
    ejercicios = db.relationship(
        "Ejercicio", back_populates="usuario", cascade="all, delete-orphan"
    )
    suenos = db.relationship(
        "RegistroSueno", back_populates="usuario", cascade="all, delete-orphan"
    )
    etiquetas = db.relationship(
        "Etiqueta", back_populates="usuario", cascade="all, delete-orphan"
    )
    apuntes = db.relationship(
        "Apunte", back_populates="usuario", cascade="all, delete-orphan"
    )
    registros_sintomas = db.relationship(
        "RegistroSintomas", back_populates="usuario", cascade="all, delete-orphan"
    )
    medicamentos = db.relationship(
        "Medicamento", back_populates="usuario", cascade="all, delete-orphan"
    )
    eventos = db.relationship(
        "Evento", back_populates="usuario", cascade="all, delete-orphan"
    )
    conexion_google = db.relationship(
        "ConexionGoogle", back_populates="usuario", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("tema IN ('oscuro', 'claro')", name="ck_usuario_tema"),
    )

    def establecer_password(self, password):
        self.password_hash = generate_password_hash(password)

    def comprobar_password(self, password):
        return check_password_hash(self.password_hash, password)

    def ahora(self):
        """Fecha y hora actual en la zona horaria del usuario."""
        return datetime.now(ZoneInfo(self.zona_horaria))

    def hoy(self):
        """Fecha de hoy en la zona horaria del usuario (no la del servidor)."""
        return self.ahora().date()

    def __repr__(self):
        return f"<Usuario {self.id} {self.email}>"


@login_manager.user_loader
def cargar_usuario(usuario_id):
    return db.session.get(Usuario, int(usuario_id))


# ──────────────────────────────────────────────────────────────
# Tareas
# ──────────────────────────────────────────────────────────────

class Tarea(MarcasTiempo, db.Model):
    __tablename__ = "tareas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titulo = db.Column(db.String(200), nullable=False)
    notas = db.Column(db.Text)
    fecha = db.Column(db.Date, index=True)          # día previsto (opcional)
    coste_energia = db.Column(db.SmallInteger)      # 1–5, para las cucharas
    completada = db.Column(db.Boolean, nullable=False, default=False)
    completada_en = db.Column(db.DateTime(timezone=True))

    usuario = db.relationship("Usuario", back_populates="tareas")

    __table_args__ = (
        CheckConstraint(
            "coste_energia IS NULL OR coste_energia BETWEEN 1 AND 5",
            name="ck_tarea_coste_energia",
        ),
    )

    def marcar_completada(self, completada=True):
        self.completada = completada
        self.completada_en = ahora_utc() if completada else None

    def __repr__(self):
        return f"<Tarea {self.id} {self.titulo!r}>"


# ──────────────────────────────────────────────────────────────
# Notas
# ──────────────────────────────────────────────────────────────

class Nota(MarcasTiempo, db.Model):
    __tablename__ = "notas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titulo = db.Column(db.String(200))
    contenido = db.Column(db.Text, nullable=False, default="")
    fijada = db.Column(db.Boolean, nullable=False, default=False)

    usuario = db.relationship("Usuario", back_populates="notas")
    etiquetas = db.relationship(
        "Etiqueta", secondary=nota_etiquetas, back_populates="notas"
    )

    def __repr__(self):
        return f"<Nota {self.id} {self.titulo!r}>"


# ──────────────────────────────────────────────────────────────
# Diario
# ──────────────────────────────────────────────────────────────

class EntradaDiario(MarcasTiempo, db.Model):
    __tablename__ = "entradas_diario"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Fecha del día del que se escribe (puede ser un día pasado),
    # distinta de creado_en, que es cuándo se escribió.
    fecha = db.Column(db.Date, nullable=False, default=date.today, index=True)
    contenido = db.Column(TextoCifrado, nullable=False)
    estado_animo = db.Column(db.SmallInteger)       # 1–5, opcional
    pregunta_guia = db.Column(db.String(200))       # si usó una pregunta guía

    usuario = db.relationship("Usuario", back_populates="entradas_diario")
    etiquetas = db.relationship(
        "Etiqueta", secondary=diario_etiquetas, back_populates="entradas_diario"
    )

    __table_args__ = (
        CheckConstraint(
            "estado_animo IS NULL OR estado_animo BETWEEN 1 AND 5",
            name="ck_diario_estado_animo",
        ),
    )

    def __repr__(self):
        return f"<EntradaDiario {self.id} {self.fecha}>"


# ──────────────────────────────────────────────────────────────
# Lista de la compra
# ──────────────────────────────────────────────────────────────

class ItemCompra(MarcasTiempo, db.Model):
    __tablename__ = "items_compra"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(120), nullable=False)
    cantidad = db.Column(db.String(40))             # texto libre: "2", "1 kg"…
    comprado = db.Column(db.Boolean, nullable=False, default=False)

    usuario = db.relationship("Usuario", back_populates="items_compra")

    def __repr__(self):
        return f"<ItemCompra {self.id} {self.nombre!r}>"


class ProductoFrecuente(db.Model):
    """Lo que el usuario suele comprar, para ofrecérselo con un toque."""

    __tablename__ = "productos_frecuentes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clave = db.Column(db.String(120), nullable=False)    # nombre normalizado: «platanos»
    nombre = db.Column(db.String(120), nullable=False)   # como lo escribió: «Plátanos»
    veces = db.Column(db.Integer, nullable=False, default=1)
    ultima_vez = db.Column(db.DateTime(timezone=True), nullable=False, default=ahora_utc)

    usuario = db.relationship("Usuario", back_populates="productos_frecuentes")

    __table_args__ = (
        UniqueConstraint("usuario_id", "clave", name="uq_producto_frecuente"),
    )


# ──────────────────────────────────────────────────────────────
# Captura rápida (bandeja de entrada)
# ──────────────────────────────────────────────────────────────

class Apunte(MarcasTiempo, db.Model):
    """Algo apuntado deprisa, sin decidir aún si es tarea, nota o
    compra. Se queda en la bandeja hasta que se ordena."""

    __tablename__ = "apuntes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    texto = db.Column(db.Text, nullable=False)

    usuario = db.relationship("Usuario", back_populates="apuntes")

    def __repr__(self):
        return f"<Apunte {self.id}>"


# ──────────────────────────────────────────────────────────────
# Eventos y citas médicas
# ──────────────────────────────────────────────────────────────

class Evento(MarcasTiempo, db.Model):
    """Un plan o una cita. Las citas médicas tienen además las
    preguntas que llevar y lo que dijo el médico. Los textos van
    cifrados: «Psiquiatra, 10:00» ya dice mucho de alguien."""

    __tablename__ = "eventos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(10), nullable=False, default="evento")   # evento | cita
    titulo = db.Column(TextoCifrado, nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time)        # vacía = todo el día
    hora_fin = db.Column(db.Time)
    lugar = db.Column(TextoCifrado)
    notas = db.Column(TextoCifrado)
    coste_energia = db.Column(db.SmallInteger)      # cucharas, como las tareas

    # Solo citas médicas
    profesional = db.Column(TextoCifrado)   # "Dra. López, reumatología"
    preguntas = db.Column(TextoCifrado)     # una por línea
    resumen = db.Column(TextoCifrado)       # qué dijo, pruebas, cambios…

    # Sincronización con Google Calendar
    google_id = db.Column(db.String(255), index=True)
    origen = db.Column(db.String(10), nullable=False, default="app", server_default="app")  # app | google

    usuario = db.relationship("Usuario", back_populates="eventos")

    __table_args__ = (
        CheckConstraint("tipo IN ('evento', 'cita')", name="ck_evento_tipo"),
        CheckConstraint(
            "coste_energia IS NULL OR coste_energia BETWEEN 1 AND 5",
            name="ck_evento_coste_energia",
        ),
    )

    @property
    def es_cita(self):
        return self.tipo == "cita"

    def lista_preguntas(self):
        """Preguntas para el médico, una por línea (sin guiones ni viñetas)."""
        lineas = (linea.strip(" -•*\t") for linea in (self.preguntas or "").splitlines())
        return [linea for linea in lineas if linea]

    def __repr__(self):
        return f"<Evento {self.id} {self.fecha}>"


class ConexionGoogle(MarcasTiempo, db.Model):
    """Permiso para usar el Google Calendar del usuario. Los tokens
    van cifrados: con ellos se podría leer y cambiar su calendario."""

    __tablename__ = "conexiones_google"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email = db.Column(db.String(255))
    refresh_token = db.Column(TextoCifrado, nullable=False)
    access_token = db.Column(TextoCifrado)
    caduca_en = db.Column(db.DateTime(timezone=True))
    # Privacidad: por defecto las citas médicas llegan a Google solo
    # como «Cita médica», sin decir con quién ni para qué.
    detalle_citas = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    ultima_sincronizacion = db.Column(db.DateTime(timezone=True))

    usuario = db.relationship("Usuario", back_populates="conexion_google")


# ──────────────────────────────────────────────────────────────
# Salud: registro diario de síntomas
# ──────────────────────────────────────────────────────────────

# Escalas de 0 a 10 (como la escala de dolor que usan en consulta).
# El significado de cada una está en salud.py (SINTOMAS).
COLUMNAS_SINTOMAS = ("dolor", "fatiga", "sueno", "niebla", "rigidez", "animo")


class RegistroSintomas(MarcasTiempo, db.Model):
    """Cómo está el cuerpo un día concreto. Uno por usuario y día."""

    __tablename__ = "registros_sintomas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False)
    dolor = db.Column(db.SmallInteger)
    fatiga = db.Column(db.SmallInteger)
    sueno = db.Column(db.SmallInteger)      # calidad: 10 = he dormido genial
    niebla = db.Column(db.SmallInteger)
    rigidez = db.Column(db.SmallInteger)
    animo = db.Column(db.SmallInteger)      # 10 = muy buen ánimo
    notas = db.Column(TextoCifrado)         # texto libre: cifrado

    usuario = db.relationship("Usuario", back_populates="registros_sintomas")

    __table_args__ = (
        UniqueConstraint("usuario_id", "fecha", name="uq_sintomas_usuario_fecha"),
        *(
            CheckConstraint(
                f"{columna} IS NULL OR {columna} BETWEEN 0 AND 10",
                name=f"ck_sintomas_{columna}",
            )
            for columna in COLUMNAS_SINTOMAS
        ),
    )

    def esta_vacio(self):
        return all(getattr(self, c) is None for c in COLUMNAS_SINTOMAS) and not self.notas

    def __repr__(self):
        return f"<RegistroSintomas {self.id} {self.fecha}>"


# ──────────────────────────────────────────────────────────────
# Salud: medicación
# ──────────────────────────────────────────────────────────────

class Medicamento(MarcasTiempo, db.Model):
    """Un medicamento con sus horas de toma. Nombre, dosis e
    instrucciones van cifrados: dicen mucho de la salud de alguien."""

    __tablename__ = "medicamentos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = db.Column(TextoCifrado, nullable=False)
    dosis = db.Column(TextoCifrado)                 # "75 mg", "1 pastilla"…
    instrucciones = db.Column(TextoCifrado)         # "con comida", "en ayunas"…
    activo = db.Column(db.Boolean, nullable=False, default=True)   # pausado = False

    usuario = db.relationship("Usuario", back_populates="medicamentos")
    horas = db.relationship(
        "HoraToma",
        back_populates="medicamento",
        cascade="all, delete-orphan",
        order_by="HoraToma.hora",
    )
    tomas = db.relationship(
        "Toma", back_populates="medicamento", cascade="all, delete-orphan"
    )

    @property
    def a_demanda(self):
        """Sin horas fijas: se toma solo cuando hace falta."""
        return not self.horas

    def __repr__(self):
        return f"<Medicamento {self.id}>"


class HoraToma(db.Model):
    """Hora del día a la que toca tomar un medicamento (hora local)."""

    __tablename__ = "horas_toma"

    id = db.Column(db.Integer, primary_key=True)
    medicamento_id = db.Column(
        db.Integer,
        db.ForeignKey("medicamentos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hora = db.Column(db.Time, nullable=False)

    medicamento = db.relationship("Medicamento", back_populates="horas")

    __table_args__ = (
        UniqueConstraint("medicamento_id", "hora", name="uq_hora_toma"),
    )


class Toma(db.Model):
    """Registro de una toma: hecha o saltada. Las de horario fijo
    llevan la hora prevista; las «a demanda», no."""

    __tablename__ = "tomas"

    id = db.Column(db.Integer, primary_key=True)
    medicamento_id = db.Column(
        db.Integer,
        db.ForeignKey("medicamentos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_prevista = db.Column(db.Time)
    estado = db.Column(db.String(10), nullable=False, default="tomada")
    registrada_en = db.Column(db.DateTime(timezone=True), nullable=False, default=ahora_utc)

    medicamento = db.relationship("Medicamento", back_populates="tomas")

    __table_args__ = (
        UniqueConstraint("medicamento_id", "fecha", "hora_prevista", name="uq_toma_prevista"),
        CheckConstraint("estado IN ('tomada', 'saltada')", name="ck_toma_estado"),
    )


# ──────────────────────────────────────────────────────────────
# Nutrición
# ──────────────────────────────────────────────────────────────

def _usuario_fk():
    return db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class PlanNutricion(MarcasTiempo, db.Model):
    """Datos para calcular lo que necesita el cuerpo y los objetivos
    diarios (que el usuario puede ajustar a mano)."""

    __tablename__ = "planes_nutricion"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    sexo = db.Column(db.String(10))                 # mujer | hombre (para la fórmula)
    edad = db.Column(db.SmallInteger)
    altura_cm = db.Column(db.SmallInteger)
    actividad = db.Column(db.String(12))            # sedentaria | ligera | moderada | alta
    objetivo = db.Column(db.String(10))             # perder | mantener | ganar

    kcal = db.Column(db.Integer)
    proteinas_g = db.Column(db.Integer)
    hidratos_g = db.Column(db.Integer)
    grasas_g = db.Column(db.Integer)

    usuario = db.relationship("Usuario", back_populates="plan_nutricion")

    __table_args__ = (
        CheckConstraint("sexo IS NULL OR sexo IN ('mujer', 'hombre')", name="ck_plan_sexo"),
        CheckConstraint(
            "actividad IS NULL OR actividad IN ('sedentaria', 'ligera', 'moderada', 'alta')",
            name="ck_plan_actividad",
        ),
        CheckConstraint(
            "objetivo IS NULL OR objetivo IN ('perder', 'mantener', 'ganar')", name="ck_plan_objetivo"
        ),
    )


class Alimento(MarcasTiempo, db.Model):
    """Un alimento guardado por el usuario, con sus valores por 100 g."""

    __tablename__ = "alimentos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    nombre = db.Column(db.String(120), nullable=False)
    kcal = db.Column(db.Float, nullable=False)
    proteinas = db.Column(db.Float, nullable=False, default=0)
    hidratos = db.Column(db.Float, nullable=False, default=0)
    grasas = db.Column(db.Float, nullable=False, default=0)
    racion_g = db.Column(db.Float)                  # ración habitual, para proponerla

    usuario = db.relationship("Usuario", back_populates="alimentos")


MOMENTOS_COMIDA = ("desayuno", "media_manana", "comida", "merienda", "cena", "picoteo")


class Comida(MarcasTiempo, db.Model):
    """Algo que se ha comido. Los valores son los totales de lo comido."""

    __tablename__ = "comidas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False, index=True)
    momento = db.Column(db.String(15), nullable=False, default="comida")
    nombre = db.Column(db.String(160), nullable=False)
    gramos = db.Column(db.Float)
    kcal = db.Column(db.Float, nullable=False, default=0)
    proteinas = db.Column(db.Float, nullable=False, default=0)
    hidratos = db.Column(db.Float, nullable=False, default=0)
    grasas = db.Column(db.Float, nullable=False, default=0)

    usuario = db.relationship("Usuario", back_populates="comidas")

    __table_args__ = (
        CheckConstraint(
            "momento IN ('desayuno', 'media_manana', 'comida', 'merienda', 'cena', 'picoteo')",
            name="ck_comida_momento",
        ),
    )


class RecetaGuardada(MarcasTiempo, db.Model):
    """Una receta (de la IA) que el usuario ha querido guardar."""

    __tablename__ = "recetas_guardadas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    titulo = db.Column(db.String(200), nullable=False)
    datos = db.Column(db.JSON, nullable=False)       # ingredientes, pasos, macros…

    usuario = db.relationship("Usuario", back_populates="recetas")


class UsoIA(db.Model):
    """Cuántas veces al día se ha usado la IA (para limitar el gasto)."""

    __tablename__ = "usos_ia"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False)
    veces = db.Column(db.Integer, nullable=False, default=0)

    usuario = db.relationship("Usuario", back_populates="usos_ia")

    __table_args__ = (UniqueConstraint("usuario_id", "fecha", name="uq_uso_ia_dia"),)


class RegistroPeso(MarcasTiempo, db.Model):
    __tablename__ = "registros_peso"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False)
    kg = db.Column(db.Float, nullable=False)

    usuario = db.relationship("Usuario", back_populates="pesos")

    __table_args__ = (
        UniqueConstraint("usuario_id", "fecha", name="uq_peso_usuario_fecha"),
        CheckConstraint("kg > 20 AND kg < 400", name="ck_peso_razonable"),
    )


# ──────────────────────────────────────────────────────────────
# Cuerpo: actividad, ejercicio y sueño
# ──────────────────────────────────────────────────────────────

ORIGENES = ("manual", "reloj")


class RegistroActividad(MarcasTiempo, db.Model):
    """Lo que se ha movido el cuerpo un día. Uno por usuario y día."""

    __tablename__ = "registros_actividad"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False)
    pasos = db.Column(db.Integer)
    minutos_activos = db.Column(db.Integer)
    kcal_activas = db.Column(db.Integer)
    distancia_km = db.Column(db.Float)
    origen = db.Column(db.String(10), nullable=False, default="manual")

    usuario = db.relationship("Usuario", back_populates="actividades")

    __table_args__ = (
        UniqueConstraint("usuario_id", "fecha", name="uq_actividad_usuario_fecha"),
        CheckConstraint("pasos IS NULL OR pasos BETWEEN 0 AND 200000", name="ck_actividad_pasos"),
    )


class Ejercicio(MarcasTiempo, db.Model):
    __tablename__ = "ejercicios"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(80), nullable=False)        # «Paseo», «Yoga suave»…
    minutos = db.Column(db.Integer, nullable=False)
    kcal = db.Column(db.Integer)
    intensidad = db.Column(db.SmallInteger)                # 1 suave · 2 media · 3 intensa
    notas = db.Column(db.Text)
    origen = db.Column(db.String(10), nullable=False, default="manual")

    usuario = db.relationship("Usuario", back_populates="ejercicios")

    __table_args__ = (
        CheckConstraint("minutos BETWEEN 1 AND 1440", name="ck_ejercicio_minutos"),
        CheckConstraint("intensidad IS NULL OR intensidad BETWEEN 1 AND 3", name="ck_ejercicio_intensidad"),
    )


class RegistroSueno(MarcasTiempo, db.Model):
    """Una noche de sueño. La fecha es la del día en que te despiertas."""

    __tablename__ = "registros_sueno"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = _usuario_fk()
    fecha = db.Column(db.Date, nullable=False)
    minutos_dormido = db.Column(db.Integer)
    hora_acostarse = db.Column(db.Time)
    hora_levantarse = db.Column(db.Time)
    minutos_profundo = db.Column(db.Integer)              # fases (si las da el reloj)
    minutos_rem = db.Column(db.Integer)
    minutos_ligero = db.Column(db.Integer)
    minutos_despierto = db.Column(db.Integer)
    calidad = db.Column(db.SmallInteger)                  # 1–5, cómo te has levantado
    despertares = db.Column(db.SmallInteger)
    origen = db.Column(db.String(10), nullable=False, default="manual")

    usuario = db.relationship("Usuario", back_populates="suenos")

    __table_args__ = (
        UniqueConstraint("usuario_id", "fecha", name="uq_sueno_usuario_fecha"),
        CheckConstraint("minutos_dormido IS NULL OR minutos_dormido BETWEEN 0 AND 1440", name="ck_sueno_minutos"),
        CheckConstraint("calidad IS NULL OR calidad BETWEEN 1 AND 5", name="ck_sueno_calidad"),
    )


# ──────────────────────────────────────────────────────────────
# Etiquetas
# ──────────────────────────────────────────────────────────────

class Etiqueta(MarcasTiempo, db.Model):
    __tablename__ = "etiquetas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(40), nullable=False)

    usuario = db.relationship("Usuario", back_populates="etiquetas")
    notas = db.relationship(
        "Nota", secondary=nota_etiquetas, back_populates="etiquetas"
    )
    entradas_diario = db.relationship(
        "EntradaDiario", secondary=diario_etiquetas, back_populates="etiquetas"
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "nombre", name="uq_etiqueta_usuario_nombre"),
    )

    def __repr__(self):
        return f"<Etiqueta {self.id} {self.nombre!r}>"