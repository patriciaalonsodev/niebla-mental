# ══════════════════════════════════════════════════════════════
#  App de organización · formularios.py
#  Formularios (Flask-WTF): validación y protección CSRF
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    DecimalField,
    FieldList,
    IntegerField,
    BooleanField,
    DateField,
    EmailField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TextAreaField,
    TimeField,
)
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError


def _limpiar_email(valor):
    """Quita espacios (el móvil suele añadir uno al autocompletar) y
    pasa a minúsculas, para que Patz@Mail.com y patz@mail.com sean igual."""
    return valor.strip().lower() if isinstance(valor, str) else valor


def _limpiar_texto(valor):
    return valor.strip() if isinstance(valor, str) else valor


# ──────────────────────────────────────────────────────────────
# Cuenta
# ──────────────────────────────────────────────────────────────

class FormularioRegistro(FlaskForm):
    nombre = StringField(
        "¿Cómo te llamas?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe tu nombre."), Length(max=80)],
    )
    email = EmailField(
        "Email",
        filters=[_limpiar_email],
        validators=[
            DataRequired("Escribe tu email."),
            Email("Ese email no parece válido."),
            Length(max=255),
        ],
    )
    password = PasswordField(
        "Contraseña",
        validators=[
            DataRequired("Escribe una contraseña."),
            Length(min=8, message="Usa al menos 8 caracteres."),
        ],
    )
    password2 = PasswordField(
        "Repite la contraseña",
        validators=[
            DataRequired("Repite la contraseña."),
            EqualTo("password", "Las contraseñas no coinciden."),
        ],
    )
    acepta_privacidad = BooleanField(
        "He leído y acepto la política de privacidad",
        validators=[DataRequired("Necesitas aceptarla para crear la cuenta.")],
    )
    # RGPD art. 9: consentimiento explícito y separado para datos de salud
    consiente_salud = BooleanField(
        "Doy mi consentimiento explícito para que la app guarde mis datos "
        "de salud (síntomas, medicación y diario), cifrados y solo para mí",
        validators=[DataRequired("Sin este consentimiento la app no puede guardar tus datos de salud.")],
    )


class FormularioLogin(FlaskForm):
    email = EmailField(
        "Email",
        filters=[_limpiar_email],
        validators=[DataRequired("Escribe tu email."), Email("Ese email no parece válido.")],
    )
    password = PasswordField(
        "Contraseña", validators=[DataRequired("Escribe tu contraseña.")]
    )
    # Marcado por defecto: así no hay que recordar la contraseña cada día
    recordar = BooleanField("Mantener la sesión abierta", default=True)


# ──────────────────────────────────────────────────────────────
# Tareas
# ──────────────────────────────────────────────────────────────

def _entero_o_nada(valor):
    """"" o None → None (sin indicar); "3" → 3."""
    if valor in ("", None):
        return None
    return int(valor)


OPCIONES_CUCHARAS = [SelectChoice("", "Sin indicar")] + [
    SelectChoice(str(n), str(n)) for n in range(1, 6)
]


class FormularioTarea(FlaskForm):
    titulo = StringField(
        "¿Qué tienes que hacer?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe la tarea."), Length(max=200)],
    )
    fecha = DateField("¿Para cuándo?", validators=[Optional()])
    coste_energia = RadioField(
        "¿Cuántas cucharas te costará?",
        choices=OPCIONES_CUCHARAS,
        coerce=_entero_o_nada,
        default="",
    )
    notas = TextAreaField("Notas", filters=[_limpiar_texto], validators=[Optional()])


# ──────────────────────────────────────────────────────────────
# Notas
# ──────────────────────────────────────────────────────────────

class FormularioNota(FlaskForm):
    titulo = StringField(
        "Título (opcional)",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=200)],
    )
    contenido = TextAreaField(
        "Nota",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe algo en la nota.")],
    )
    etiquetas = StringField(
        "Etiquetas (opcional)",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=300)],
        description="Separadas por comas: médico, ideas, casa",
    )
    fijada = BooleanField("📌 Fijar arriba")


# ──────────────────────────────────────────────────────────────
# Lista de la compra
# ──────────────────────────────────────────────────────────────

class FormularioCompra(FlaskForm):
    nombre = StringField(
        "¿Qué hay que comprar?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe qué hay que comprar."), Length(max=120)],
    )
    cantidad = StringField(
        "Cantidad",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=40)],
    )


# ──────────────────────────────────────────────────────────────
# Captura rápida
# ──────────────────────────────────────────────────────────────

class FormularioApunte(FlaskForm):
    texto = TextAreaField(
        "¿Qué no quieres olvidar?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe algo para apuntarlo."), Length(max=2000)],
    )


# ──────────────────────────────────────────────────────────────
# Salud: síntomas del día
# ──────────────────────────────────────────────────────────────

OPCIONES_ESCALA = [SelectChoice("", "—")] + [SelectChoice(str(n), str(n)) for n in range(11)]


def _escala(pregunta):
    """Escala 0–10 opcional: si no se marca nada, queda «sin indicar»."""
    return RadioField(
        pregunta,
        choices=OPCIONES_ESCALA,
        coerce=_entero_o_nada,
        default="",
        validators=[Optional()],
    )


class FormularioSintomas(FlaskForm):
    # Las preguntas y los extremos de cada escala están en salud.SINTOMAS
    dolor = _escala("Dolor")
    fatiga = _escala("Cansancio")
    sueno = _escala("Sueño")
    niebla = _escala("Niebla mental")
    rigidez = _escala("Rigidez")
    animo = _escala("Ánimo")
    notas = TextAreaField(
        "¿Algo más?",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=4000)],
        description="Dónde te duele, qué ha podido influir… Se guarda cifrado.",
    )


# ──────────────────────────────────────────────────────────────
# Salud: medicación
# ──────────────────────────────────────────────────────────────

MAX_HORAS_TOMA = 4


class FormularioMedicamento(FlaskForm):
    nombre = StringField(
        "Nombre del medicamento",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe el nombre del medicamento."), Length(max=120)],
    )
    dosis = StringField(
        "Dosis",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=60)],
        description="Por ejemplo: 75 mg, 1 pastilla, 20 gotas",
    )
    horas = FieldList(
        TimeField("Hora", validators=[Optional()]),
        min_entries=MAX_HORAS_TOMA,
        max_entries=MAX_HORAS_TOMA,
    )
    instrucciones = StringField(
        "Instrucciones",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=200)],
        description="Por ejemplo: con comida, en ayunas, antes de dormir",
    )

    def horas_elegidas(self):
        """Horas rellenadas, sin repetir y ordenadas."""
        return sorted({campo.data for campo in self.horas if campo.data})


# ──────────────────────────────────────────────────────────────
# Diario
# ──────────────────────────────────────────────────────────────

ESTADOS_ANIMO = {1: ("😣", "Muy mal"), 2: ("😕", "Mal"), 3: ("😐", "Regular"), 4: ("🙂", "Bien"), 5: ("😄", "Muy bien")}

PREGUNTAS_GUIA = [
    "¿Qué ha sido lo más difícil de hoy?",
    "¿Qué te ha sentado bien hoy?",
    "¿Hay algo pequeño que te haya hecho sonreír?",
    "¿Qué te ha quitado energía hoy?",
    "¿Qué has logrado hoy, aunque sea pequeño?",
    "¿Qué le dirías a alguien a quien quieres si hubiera tenido tu día?",
    "¿Qué necesitas mañana para estar un poco mejor?",
    "¿Qué te preocupa ahora mismo?",
    "¿Por qué tres cosas sientes gratitud hoy?",
    "¿Cómo ha estado tu cuerpo hoy, y qué te ha pedido?",
]


class FormularioDiario(FlaskForm):
    fecha = DateField("Día", validators=[DataRequired("Elige el día.")])
    estado_animo = RadioField(
        "¿Cómo te sientes?",
        choices=[SelectChoice("", "Sin indicar")]
        + [SelectChoice(str(n), emoji) for n, (emoji, _) in ESTADOS_ANIMO.items()],
        coerce=_entero_o_nada,
        default="",
        validators=[Optional()],
    )
    pregunta_guia = SelectField(
        "Elige una pregunta",
        choices=[SelectChoice("", "Escribir libremente")] + [SelectChoice(p, p) for p in PREGUNTAS_GUIA],
        default="",
        validate_choice=False,          # al editar puede quedar una pregunta antigua
        filters=[lambda v: v or None],
    )
    contenido = TextAreaField(
        "Escribe lo que quieras",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe algo para guardar la entrada."), Length(max=20000)],
        description="Solo lo puedes leer tú: se guarda cifrado.",
    )
    etiquetas = StringField(
        "Etiquetas",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=200)],
        description="Separadas por comas: brote, trabajo, familia",
    )


# ──────────────────────────────────────────────────────────────
# Eventos y citas médicas
# ──────────────────────────────────────────────────────────────

class FormularioEvento(FlaskForm):
    tipo = RadioField(
        "¿Qué es?",
        choices=[SelectChoice("evento", "📅 Evento o plan"), SelectChoice("cita", "🩺 Cita médica")],
        default="evento",
    )
    titulo = StringField(
        "Título",
        filters=[_limpiar_texto],
        validators=[DataRequired("Ponle un título."), Length(max=200)],
    )
    fecha = DateField("Día", validators=[DataRequired("Elige el día.")])
    hora_inicio = TimeField("Empieza", validators=[Optional()])
    hora_fin = TimeField("Termina", validators=[Optional()])
    lugar = StringField("Lugar", filters=[_limpiar_texto], validators=[Optional(), Length(max=200)])
    coste_energia = RadioField(
        "¿Cuántas cucharas te costará?",
        choices=OPCIONES_CUCHARAS,
        coerce=_entero_o_nada,
        default="",
    )
    notas = TextAreaField("Notas", filters=[_limpiar_texto], validators=[Optional(), Length(max=4000)])

    # Solo citas médicas
    profesional = StringField(
        "Profesional o especialidad",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=200)],
        description="Por ejemplo: Dra. López, reumatología",
    )
    preguntas = TextAreaField(
        "Preguntas que quieres hacer",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=4000)],
        description="Una por línea. Apúntalas cuando te acuerdes y llévalas a la consulta.",
    )
    resumen = TextAreaField(
        "¿Qué te dijeron?",
        filters=[_limpiar_texto],
        validators=[Optional(), Length(max=8000)],
        description="Después de la cita: diagnóstico, pruebas, cambios de medicación…",
    )

    def validate_hora_fin(self, campo):
        if campo.data and not self.hora_inicio.data:
            raise ValidationError("Pon también la hora de inicio.")
        if campo.data and self.hora_inicio.data and campo.data < self.hora_inicio.data:
            raise ValidationError("Tiene que ser después de la hora de inicio.")


# ──────────────────────────────────────────────────────────────
# Perfil
# ──────────────────────────────────────────────────────────────

def _zonas_horarias():
    from zoneinfo import available_timezones
    # Solo las de verdad (Europe/Madrid, America/Bogota…), no las antiguas tipo «EST»
    zonas = sorted(z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/")))
    return [SelectChoice(z, z.replace("_", " ")) for z in zonas]


class FormularioPerfil(FlaskForm):
    nombre = StringField(
        "¿Cómo quieres que te llame?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Escribe tu nombre."), Length(max=80)],
    )
    tema = RadioField(
        "Aspecto",
        choices=[SelectChoice("oscuro", "🌙 Oscuro"), SelectChoice("claro", "☀️ Claro")],
        default="oscuro",
    )
    zona_horaria = SelectField(
        "Zona horaria",
        description="Para que «hoy» y las horas de la medicación sean las tuyas.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zona_horaria.choices = _zonas_horarias()


class FormularioFoto(FlaskForm):
    foto = FileField(
        "Foto de perfil",
        validators=[
            FileRequired("Elige una foto."),
            FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Tiene que ser una foto (JPG, PNG o WebP)."),
        ],
    )


# ──────────────────────────────────────────────────────────────
# Nutrición
# ──────────────────────────────────────────────────────────────

class _DecimalConComa(DecimalField):
    def process_formdata(self, valuelist):
        if valuelist:
            valuelist = [v.replace(",", ".").strip() for v in valuelist]
        super().process_formdata(valuelist)


def _numero(etiqueta, maximo, obligatorio=False, **extra):
    return _DecimalConComa(
        etiqueta,
        places=None,
        render_kw={"inputmode": "decimal"},     # teclado numérico en el móvil
        validators=[
            (DataRequired("Escribe un número.") if obligatorio else Optional()),
            NumberRange(min=0, max=maximo, message=f"Entre 0 y {maximo}."),
        ],
        **extra,
    )


class FormularioPlanNutricion(FlaskForm):
    sexo = RadioField(
        "Sexo (para la fórmula)",
        choices=[SelectChoice("mujer", "Mujer"), SelectChoice("hombre", "Hombre")],
        validators=[Optional()],
    )
    edad = IntegerField("Edad", validators=[Optional(), NumberRange(min=14, max=110, message="Entre 14 y 110.")])
    altura_cm = IntegerField("Altura (cm)", validators=[Optional(), NumberRange(min=120, max=230, message="Entre 120 y 230 cm.")])
    peso = _numero("Peso actual (kg)", 400, description="Se guarda también en tu registro de peso.")
    actividad = SelectField(
        "¿Cuánto te mueves?",
        choices=[
            SelectChoice("sedentaria", "Poco: paso casi todo el día en reposo"),
            SelectChoice("ligera", "Algo: paseos o tareas de casa"),
            SelectChoice("moderada", "Bastante: ejercicio 3–5 días por semana"),
            SelectChoice("alta", "Mucho: ejercicio intenso casi a diario"),
        ],
        default="sedentaria",
    )
    objetivo = RadioField(
        "¿Qué quieres?",
        choices=[
            SelectChoice("perder", "Perder peso"),
            SelectChoice("mantener", "Mantenerme"),
            SelectChoice("ganar", "Ganar peso o músculo"),
        ],
        default="mantener",
    )
    # Objetivos diarios (se calculan, pero se pueden tocar)
    kcal = IntegerField("Calorías al día", validators=[Optional(), NumberRange(min=800, max=6000, message="Entre 800 y 6000.")])
    proteinas_g = IntegerField("Proteínas (g)", validators=[Optional(), NumberRange(min=0, max=500)])
    hidratos_g = IntegerField("Hidratos (g)", validators=[Optional(), NumberRange(min=0, max=900)])
    grasas_g = IntegerField("Grasas (g)", validators=[Optional(), NumberRange(min=0, max=400)])


class FormularioComida(FlaskForm):
    fecha = DateField("Día", validators=[DataRequired()])
    momento = SelectField("¿Cuándo?", choices=[
        SelectChoice("desayuno", "☕ Desayuno"),
        SelectChoice("media_manana", "🍎 Media mañana"),
        SelectChoice("comida", "🍲 Comida"),
        SelectChoice("merienda", "🥪 Merienda"),
        SelectChoice("cena", "🌙 Cena"),
        SelectChoice("picoteo", "🍫 Picoteo"),
    ], default="comida")
    alimento = SelectField("De mis alimentos", coerce=_entero_o_nada, validate_choice=False, default="")
    gramos = _numero("Cantidad (g)", 5000)
    nombre = StringField("¿Qué has comido?", filters=[_limpiar_texto], validators=[Optional(), Length(max=160)])
    kcal = _numero("Calorías", 10000)
    proteinas = _numero("Proteínas (g)", 1000)
    hidratos = _numero("Hidratos (g)", 1000)
    grasas = _numero("Grasas (g)", 1000)
    guardar_alimento = BooleanField("Guardarlo en «mis alimentos» (si has puesto los gramos)")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.alimento.data:
            if not self.gramos.data:
                self.gramos.errors.append("¿Cuántos gramos?")
                return False
            return True
        ok = True
        if not self.nombre.data:
            self.nombre.errors.append("Escribe qué has comido o elige uno de tus alimentos.")
            ok = False
        if self.kcal.data is None:
            self.kcal.errors.append("Pon las calorías (aunque sea aproximadas).")
            ok = False
        return ok


class FormularioAlimento(FlaskForm):
    nombre = StringField("Nombre", filters=[_limpiar_texto],
                         validators=[DataRequired("Escribe el nombre."), Length(max=120)])
    kcal = _numero("Calorías por 100 g", 1000, obligatorio=True)
    proteinas = _numero("Proteínas por 100 g", 100)
    hidratos = _numero("Hidratos por 100 g", 100)
    grasas = _numero("Grasas por 100 g", 100)
    racion_g = _numero("Ración habitual (g)", 5000, description="Opcional: para proponértela al apuntar.")


class FormularioPeso(FlaskForm):
    fecha = DateField("Día", validators=[DataRequired()])
    kg = _numero("Peso (kg)", 399, obligatorio=True)


class FormularioReceta(FlaskForm):
    peticion = TextAreaField(
        "¿Qué te apetece o qué tienes en la nevera?",
        filters=[_limpiar_texto],
        validators=[DataRequired("Cuéntame qué te apetece."), Length(max=500)],
        description="Por ejemplo: «algo con pollo y calabacín, fácil, para cenar».",
    )
    ajustar = BooleanField("Ajustarla a lo que me queda hoy de calorías y macros", default=True)


# ──────────────────────────────────────────────────────────────
# Cuerpo: actividad, ejercicio y sueño
# ──────────────────────────────────────────────────────────────

def _entero(etiqueta, minimo, maximo, **extra):
    return IntegerField(
        etiqueta,
        validators=[Optional(), NumberRange(min=minimo, max=maximo, message=f"Entre {minimo} y {maximo}.")],
        render_kw={"inputmode": "numeric"},
        **extra,
    )


class FormularioActividad(FlaskForm):
    fecha = DateField("Día", validators=[DataRequired()])
    pasos = _entero("Pasos", 0, 200000)
    minutos_activos = _entero("Minutos en movimiento", 0, 1440)
    kcal_activas = _entero("Calorías gastadas en movimiento", 0, 10000)
    distancia_km = _numero("Distancia (km)", 300)


TIPOS_EJERCICIO = ["Paseo", "Estiramientos", "Yoga suave", "Pilates", "Natación", "Bici estática",
                   "Fisioterapia", "Taichí", "Gimnasio", "Baile"]


class FormularioEjercicio(FlaskForm):
    fecha = DateField("Día", validators=[DataRequired()])
    tipo = StringField("¿Qué has hecho?", filters=[_limpiar_texto],
                       validators=[DataRequired("Escribe qué ejercicio."), Length(max=80)])
    minutos = IntegerField("Minutos", validators=[DataRequired("¿Cuántos minutos?"),
                                                  NumberRange(min=1, max=1440, message="Entre 1 y 1440.")],
                           render_kw={"inputmode": "numeric"})
    intensidad = RadioField(
        "¿Cómo de intenso?",
        choices=[SelectChoice("1", "🌱 Suave"), SelectChoice("2", "🌿 Media"), SelectChoice("3", "🔥 Intensa")],
        coerce=_entero_o_nada, default="1",
    )
    kcal = _entero("Calorías (si las sabes)", 0, 5000)


class FormularioSueno(FlaskForm):
    fecha = DateField("¿Qué día te despertaste?", validators=[DataRequired()])
    hora_acostarse = TimeField("Me dormí a las", validators=[Optional()])
    hora_levantarse = TimeField("Me desperté a las", validators=[Optional()])
    horas = _numero("Horas dormidas", 24, description="Si lo dejas vacío, se calcula con las horas de arriba.")
    calidad = RadioField(
        "¿Cómo te has levantado?",
        choices=[SelectChoice("", "—")] + [SelectChoice(str(n), e) for n, e in
                                            ((1, "😫"), (2, "😕"), (3, "😐"), (4, "🙂"), (5, "😄"))],
        coerce=_entero_o_nada, default="", validators=[Optional()],
    )
    despertares = _entero("¿Cuántas veces te despertaste?", 0, 50)


class FormularioObjetivoPasos(FlaskForm):
    objetivo_pasos = IntegerField(
        "Tu objetivo de pasos al día",
        validators=[DataRequired(), NumberRange(min=500, max=50000, message="Entre 500 y 50000.")],
        render_kw={"inputmode": "numeric"},
        description="Pon uno realista para tu energía: es mejor poco y constante.",
    )
