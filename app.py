import calendar
from datetime import datetime
from flask import (
    Flask,
    flash,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)
import io
import pandas as pd
import sqlite3

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_sesiones_lan'


# Ruta para servir el manifiesto PWA
@app.route('/manifest.json')
def manifest():
  return app.send_static_file('manifest.json')


# Función auxiliar para limpiar el .0 de los números
def limpiar_horas(valor):
  if valor is None:
    return 0
  return int(valor) if valor.is_integer() else valor


app.jinja_env.filters['limpiar_horas'] = limpiar_horas

# Diccionario para traducir los meses al español
MESES_ES = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Septiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre',
}


# Inicializar Base de Datos
def init_db():
  conn = sqlite3.connect('horas_extras.db')
  cursor = conn.cursor()

  cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nivel INTEGER NOT NULL 
        )
    ''')

  cursor.execute('''
        CREATE TABLE IF NOT EXISTS convocatorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            horas REAL NOT NULL,
            descripcion TEXT NOT NULL,
            cupos INTEGER NOT NULL DEFAULT 1,
            creado_por INTEGER,
            FOREIGN KEY(creado_por) REFERENCES usuarios(id)
        )
    ''')

  cursor.execute('''
        CREATE TABLE IF NOT EXISTS postulaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            convocatoria_id INTEGER,
            usuario_id INTEGER,
            porcentaje INTEGER DEFAULT 50,
            estado TEXT DEFAULT 'Pendiente',
            aprobado_por INTEGER,
            FOREIGN KEY(convocatoria_id) REFERENCES convocatorias(id),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY(aprobado_por) REFERENCES usuarios(id)
        )
    ''')

  cursor.execute('SELECT COUNT(*) FROM usuarios')
  if cursor.fetchone()[0] == 0:
    usuarios_prueba = [
        ('Operador', '1', 'oper1', '1234', 1),
        ('Operador', '2', 'oper2', '1234', 1),
        ('Supervisor', '1', 'super1', '1234', 2),
        ('Administrador', '1', 'admin1', '1234', 3),
    ]
    cursor.executemany(
        (
            'INSERT INTO usuarios (nombre, apellido, username, password,'
            ' nivel) VALUES (?, ?, ?, ?, ?)'
        ),
        usuarios_prueba,
    )
    conn.commit()

  conn.close()


init_db()


def verificar_franco_en_excel(username, nombre, apellido, fecha_str):
  try:
    df = pd.read_excel('francos.xlsx')
    df.columns = df.columns.str.strip().str.lower()
    df['fecha_limpia'] = pd.to_datetime(df['fecha']).dt.strftime('%Y-%m-%d')

    if 'username' in df.columns:
      registro = df[
          (df['username'].astype(str).str.strip().str.lower()
           == str(username).strip().lower())
          & (df['fecha_limpia'] == str(fecha_str))
      ]
      if not registro.empty:
        estado = str(registro.iloc[0]['estado']).strip().capitalize()
        return 100 if estado == 'Franco' else 50

    if 'nombre' in df.columns:
      registro = df[
          (df['nombre'].astype(str).str.strip().str.lower()
           == str(nombre).strip().lower())
          & (df['fecha_limpia'] == str(fecha_str))
      ]
      if not registro.empty:
        estado = str(registro.iloc[0]['estado']).strip().capitalize()
        return 100 if estado == 'Franco' else 50
  except Exception as e:
    print('Aviso: francos.xlsx no leído o ausente ->', e)

  return 50


# Plantilla HTML Principal
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sistema de Horas Extras (LAN)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
    <!-- Configuración para PWA -->
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#0d6efd">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body class="bg-light">
    <!-- CONTENEDOR DE POP-UPS / TOASTS FLOTANTES -->
    <div class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 1050;">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="toast align-items-center text-white bg-dark border-0 show shadow-lg mb-2" role="alert" aria-live="assertive" aria-atomic="true">
                        <div class="d-flex">
                            <div class="toast-body fs-6 fw-semibold">
                                🔔 {{ message }}
                            </div>
                            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                        </div>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <div class="container mt-4 mb-5">
        {% if 'user_id' not in session %}
            <!-- LOGIN -->
            <div class="row justify-content-center mt-5">
                <div class="col-md-4 card shadow p-4 bg-white">
                    <h3 class="text-center mb-3 text-primary">Iniciar Sesión</h3>
                    <form method="POST" action="/login">
                        <div class="mb-3">
                            <label class="form-label">Usuario:</label>
                            <input type="text" name="username" class="form-control" required placeholder="ej: oper1">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Contraseña:</label>
                            <input type="password" name="password" class="form-control" required placeholder="ej: 1234">
                        </div>
                        <button type="submit" class="btn btn-primary w-100">Entrar</button>
                    </form>
                    <div class="mt-3 text-muted small text-center">
                        <hr>
                        <p class="mb-1"><b>Usuarios de prueba:</b></p>
                        <p class="mb-0">Nivel 1: <code>oper1</code> / <code>1234</code></p>
                        <p class="mb-0">Nivel 1: <code>oper2</code> / <code>1234</code></p>
                        <p class="mb-0">Nivel 2: <code>super1</code> / <code>1234</code></p>
                        <p class="mb-0">Nivel 3: <code>admin1</code> / <code>1234</code></p>
                    </div>
                </div>
            </div>
        {% else %}
            <!-- PANEL PRINCIPAL -->
            <div class="card shadow p-4 bg-white">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h2>Bienvenido, {{ session['nombre'] }} {{ session['apellido'] }} 
                        <span class="badge bg-secondary fs-6">Nivel {{ session['nivel'] }}</span>
                    </h2>
                    <a href="/logout" class="btn btn-danger btn-sm">Cerrar Sesión</a>
                </div>
                <hr>

                <!-- CALENDARIO MENSUAL -->
                <div class="card p-3 mb-4 bg-light border">
                    <h4 class="text-secondary mb-3">📅 Calendario de Horas Disponibles ({{ month_name }} {{ year }})</h4>
                    <p class="text-muted small">Haz clic en los días marcados en **verde** para ver los turnos y postularte.</p>
                    <table class="table table-bordered text-center bg-white shadow-sm" style="table-layout: fixed;">
                        <thead class="table-dark">
                            <tr>
                                <th>Lun</th><th>Mar</th><th>Mié</th><th>Jue</th><th>Vie</th><th>Sáb</th><th>Dom</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for semana in cal_matrix %}
                            <tr>
                                {% for dia in semana %}
                                    {% if dia == 0 %}
                                        <td class="bg-light text-muted">-</td>
                                    {% else %}
                                        {% set fecha_str = "%04d-%02d-%02d"|format(year, month, dia) %}
                                        {% if fecha_str in dias_con_horas %}
                                            <td class="bg-success text-white fw-bold" style="cursor: pointer;" onclick="window.location.href='/dia/{{ fecha_str }}'">
                                                {{ dia }}
                                                <div class="small" style="font-size: 0.7rem;">Ver Turnos</div>
                                            </td>
                                        {% else %}
                                            <td>{{ dia }}</td>
                                        {% endif %}
                                    {% endif %}
                                {% endfor %}
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- RESUMEN MENSUAL CON DESCARGA EXCEL -->
                {% if session['nivel'] >= 2 %}
                    <div class="card p-3 mb-4 bg-light border-info">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h4 class="text-info text-dark mb-0">📈 Resumen de Equidad: Horas Acumuladas ({{ month_name }})</h4>
                            <a href="/exportar_excel" class="btn btn-success btn-sm">📥 Descargar Reporte en Excel</a>
                        </div>
                        <table class="table table-bordered table-striped bg-white mt-2">
                            <thead class="table-info">
                                <tr>
                                    <th>Operador</th>
                                    <th>Horas al 50% (Día laboral)</th>
                                    <th>Horas al 100% (Franco)</th>
                                    <th>Total General</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for resumen in resumen_operadores %}
                                <tr>
                                    <td><b>{{ resumen[0] }} {{ resumen[1] }}</b></td>
                                    <td><span class="badge bg-primary">{{ resumen[2]|limpiar_horas if resumen[2] else 0 }} hrs</span></td>
                                    <td><span class="badge bg-warning text-dark">{{ resumen[3]|limpiar_horas if resumen[3] else 0 }} hrs</span></td>
                                    <td><b>{{ ((resumen[2] if resumen[2] else 0) + (resumen[3] if resumen[3] else 0))|limpiar_horas }} hrs</b></td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="4" class="text-center text-muted">Aún no hay horas aprobadas registradas este mes.</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                {% endif %}

                <!-- NIVEL 2: Publicar Horas -->
                {% if session['nivel'] == 2 %}
                    <div class="card p-3 mb-4 bg-light border-primary">
                        <h4 class="text-primary">📝 Publicar Horas Extras y Cupos</h4>
                        <form method="POST" action="/crear_convocatoria" class="row g-3 mt-1">
                            <div class="col-md-3">
                                <label class="form-label">Fecha:</label>
                                <input type="date" name="fecha" class="form-control" required>
                            </div>
                            <div class="col-md-2">
                                <label class="form-label">Horas:</label>
                                <input type="number" step="0.5" name="horas" class="form-control" placeholder="Ej: 4" required>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Descripción / Turno:</label>
                                <input type="text" name="descripcion" class="form-control" placeholder="Ej: Refuerzo operativo" required>
                            </div>
                            <div class="col-md-1">
                                <label class="form-label">Cupo:</label>
                                <input type="number" name="cupos" class="form-control" value="1" min="1" required>
                            </div>
                            <div class="col-md-2 d-flex align-items-end">
                                <button type="submit" class="btn btn-success w-100">Publicar</button>
                            </div>
                        </form>
                    </div>
                {% endif %}

                <!-- GRILLA GENERAL -->
                <h4 class="mb-3">📋 Listado General de Horas Disponibles</h4>
                <table class="table table-bordered table-striped">
                    <thead class="table-dark">
                        <tr>
                            <th>Fecha</th>
                            <th>Horas</th>
                            <th>Descripción</th>
                            <th>Cupo</th>
                            <th>Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for conv in convocatorias %}
                        <tr>
                            <td>{{ conv[1] }}</td>
                            <td>{{ conv[2]|limpiar_horas }} hrs</td>
                            <td>{{ conv[3] }}</td>
                            <td><span class="badge bg-secondary">{{ conv[4] }} op.</span></td>
                            <td>
                                {% if session['nivel'] == 1 %}
                                    <a href="/postular/{{ conv[0] }}" class="btn btn-sm btn-primary">Postularme</a>
                                {% elif session['nivel'] >= 2 %}
                                    <a href="/eliminar_convocatoria/{{ conv[0] }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('¿Borrar convocatoria?')">Eliminar</a>
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="5" class="text-center text-muted">No hay horas disponibles cargadas.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>

                <!-- ESTADO DE POSTULACIONES -->
                <h4 class="mt-5">📊 Estado de Postulaciones</h4>
                <table class="table table-bordered table-striped mt-2">
                    <thead class="table-secondary">
                        <tr>
                            <th>Empleado</th>
                            <th>Fecha</th>
                            <th>Cantidad</th>
                            <th>Descripción</th>
                            <th>Tipo</th>
                            <th>Estado</th>
                            <th>Aprobación / Gestión (Nivel 3)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for post in postulaciones %}
                        <tr>
                            <td><b>{{ post[1] }} {{ post[2] }}</b></td>
                            <td>{{ post[3] }}</td>
                            <td>{{ post[4]|limpiar_horas }} hrs</td>
                            <td>{{ post[5] }}</td>
                            <td>
                                <span class="badge {% if post[6] == 100 %}bg-warning text-dark{% else %}bg-primary{% endif %}">
                                    {{ post[6] }}%
                                </span>
                            </td>
                            <td>
                                <span class="badge {% if post[7] == 'Aprobada' %}bg-success{% elif post[7] == 'Rechazada' %}bg-danger{% else %}bg-warning text-dark{% endif %}">
                                    {{ post[7] }}
                                </span>
                            </td>
                            <td>
                                {% if session['nivel'] == 3 and post[7] == 'Pendiente' %}
                                    <a href="/cambiar_estado/{{ post[0] }}/Aprobada" class="btn btn-sm btn-success">Aprobar</a>
                                    <a href="/cambiar_estado/{{ post[0] }}/Rechazada" class="btn btn-sm btn-danger">Rechazar</a>
                                {% elif post[8] %}
                                    <span class="text-muted small">
                                        {% if post[7] == 'Aprobada' %}
                                            Aprobada por: <b>{{ post[8] }} {{ post[9] }}</b>
                                        {% elif post[7] == 'Rechazada' %}
                                            Rechazada por: <b>{{ post[8] }} {{ post[9] }}</b>
                                        {% else %}
                                            Gestionado por: <b>{{ post[8] }} {{ post[9] }}</b>
                                        {% endif %}
                                    </span>
                                {% else %}
                                    <span class="text-muted small">-</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="7" class="text-center text-muted">No hay postulaciones registradas.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# Plantilla para ver turnos de un día específico
DIA_DETALLE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Turnos del {{ fecha }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light p-5">
    <div class="container card shadow p-4 bg-white">
        <h3 class="text-primary mb-3">📅 Horas Disponibles para el día: {{ fecha }}</h3>
        <hr>
        <table class="table table-bordered table-striped">
            <thead class="table-dark">
                <tr>
                    <th>Horas</th>
                    <th>Descripción / Turno</th>
                    <th>Cupos (Inscriptos / Máximo)</th>
                    <th>Acción</th>
                </tr>
            </thead>
            <tbody>
                {% for turno in turnos %}
                <tr>
                    <td><b>{{ turno[2]|limpiar_horas }} hrs</b></td>
                    <td>{{ turno[3] }}</td>
                    <td>
                        <span class="badge {% if turno[5] >= turno[4] %}bg-danger{% else %}bg-info text-dark{% endif %}">
                            {{ turno[5] }} / {{ turno[4] }} inscriptos
                        </span>
                    </td>
                    <td>
                        {% if session['nivel'] == 1 %}
                            {% if turno[5] >= turno[4] %}
                                <button class="btn btn-sm btn-secondary" disabled>Cupo Completo</button>
                            {% else %}
                                <a href="/postular/{{ turno[0] }}" class="btn btn-sm btn-success">Postularme</a>
                            {% endif %}
                        {% elif session['nivel'] >= 2 %}
                            <a href="/eliminar_convocatoria/{{ turno[0] }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('¿Borrar turno?')">Eliminar</a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="mt-3">
            <a href="/" class="btn btn-secondary">← Volver al Panel Principal</a>
        </div>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
  convocatorias = []
  postulaciones = []
  resumen_operadores = []
  cal_matrix = []
  month_name = ''
  year, month = datetime.now().year, datetime.now().month
  dias_con_horas = set()

  if 'user_id' in session:
    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, fecha, horas, descripcion, cupos FROM convocatorias')
    convocatorias = cursor.fetchall()

    for c in convocatorias:
      dias_con_horas.add(c[1])

    cal = calendar.Calendar(firstweekday=0)
    cal_matrix = cal.monthdayscalendar(year, month)
    month_name = MESES_ES[month]

    if session['nivel'] == 1:
      cursor.execute(
          """
                SELECT p.id, u.nombre, u.apellido, c.fecha, c.horas, c.descripcion, p.porcentaje, p.estado,
                       a.nombre, a.apellido
                FROM postulaciones p 
                JOIN convocatorias c ON p.convocatoria_id = c.id 
                JOIN usuarios u ON p.usuario_id = u.id 
                LEFT JOIN usuarios a ON p.aprobado_por = a.id
                WHERE p.usuario_id = ?
            """,
          (session['user_id'],),
      )
    else:
      cursor.execute(
          """
                SELECT p.id, u.nombre, u.apellido, c.fecha, c.horas, c.descripcion, p.porcentaje, p.estado,
                       a.nombre, a.apellido
                FROM postulaciones p 
                JOIN convocatorias c ON p.convocatoria_id = c.id 
                JOIN usuarios u ON p.usuario_id = u.id 
                LEFT JOIN usuarios a ON p.aprobado_por = a.id
            """
      )
    postulaciones = cursor.fetchall()

    if session['nivel'] >= 2:
      mes_str = f'%{year}-{month:02d}%'
      cursor.execute(
          """
                SELECT u.id, u.nombre, u.apellido,
                       SUM(CASE WHEN p.porcentaje = 50 THEN c.horas ELSE 0 END) as horas_50,
                       SUM(CASE WHEN p.porcentaje = 100 THEN c.horas ELSE 0 END) as horas_100
                FROM postulaciones p 
                JOIN usuarios u ON p.usuario_id = u.id 
                JOIN convocatorias c ON p.convocatoria_id = c.id 
                WHERE p.estado = 'Aprobada' AND c.fecha LIKE ?
                GROUP BY u.id
                ORDER BY (SUM(c.horas)) ASC
            """,
          (mes_str,),
      )
      resumen_bruto = cursor.fetchall()
      resumen_operadores = [(r[1], r[2], r[3], r[4]) for r in resumen_bruto]

    conn.close()

  return render_template_string(
      HTML_TEMPLATE,
      convocatorias=convocatorias,
      postulaciones=postulaciones,
      resumen_operadores=resumen_operadores,
      cal_matrix=cal_matrix,
      month_name=month_name,
      year=year,
      month=month,
      dias_con_horas=dias_con_horas,
  )


@app.route('/exportar_excel')
def exportار_excel():
  if 'user_id' in session and session['nivel'] >= 2:
    year, month = datetime.now().year, datetime.now().month
    mes_str = f'%{year}-{month:02d}%'
    month_name = MESES_ES[month]

    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT u.nombre, u.apellido,
                   SUM(CASE WHEN p.porcentaje = 50 THEN c.horas ELSE 0 END) as horas_50,
                   SUM(CASE WHEN p.porcentaje = 100 THEN c.horas ELSE 0 END) as horas_100,
                   SUM(c.horas) as total
            FROM postulaciones p 
            JOIN usuarios u ON p.usuario_id = u.id 
            JOIN convocatorias c ON p.convocatoria_id = c.id 
            WHERE p.estado = 'Aprobada' AND c.fecha LIKE ?
            GROUP BY u.id
            ORDER BY total ASC
        """,
        (mes_str,),
    )
    datos = cursor.fetchall()
    conn.close()

    lista_reporte = []
    for fila in datos:
      lista_reporte.append({
          'Nombre': fila[0],
          'Apellido': fila[1],
          'Horas al 50%': fila[2] if fila[2] else 0,
          'Horas al 100%': fila[3] if fila[3] else 0,
          'Total General': fila[4] if fila[4] else 0,
      })

    df = pd.DataFrame(lista_reporte)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
      df.to_excel(writer, index=False, sheet_name=f'Horas {month_name}')
    output.seek(0)

    nombre_archivo = f'Reporte_Horas_Extras_{month_name}_{year}.xlsx'
    flash('Reporte en Excel descargado correctamente.', 'success')
    return send_file(
        output,
        mimetype=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
        as_attachment=True,
        download_name=nombre_archivo,
    )

  return redirect(url_for('index'))


@app.route('/dia/<fecha>')
def ver_dia(fecha):
  if 'user_id' in session:
    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.id, c.fecha, c.horas, c.descripcion, c.cupos, 
               (SELECT COUNT(*) FROM postulaciones p WHERE p.convocatoria_id = c.id) as inscriptos
        FROM convocatorias c 
        WHERE c.fecha = ?
    """,
        (fecha,),
    )
    turnos = cursor.fetchall()
    conn.close()
    return render_template_string(
        DIA_DETALLE_TEMPLATE, fecha=fecha, turnos=turnos
    )
  return redirect(url_for('index'))


@app.route('/login', methods=['POST'])
def login():
  username = request.form['username']
  password = request.form['password']
  conn = sqlite3.connect('horas_extras.db')
  cursor = conn.cursor()
  cursor.execute(
      'SELECT id, nombre, apellido, nivel FROM usuarios WHERE username = ? AND'
      ' password = ?',
      (username, password),
  )
  user = cursor.fetchone()
  conn.close()

  if user:
    session['user_id'] = user[0]
    session['nombre'] = user[1]
    session['apellido'] = user[2]
    session['nivel'] = user[3]
    flash(f'Bienvenido al sistema, {user[1]} {user[2]}!', 'success')
    return redirect(url_for('index'))
  else:
    flash('Usuario o contraseña incorrectos.', 'danger')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
  session.clear()
  flash('Has cerrado sesión correctamente.', 'warning')
  return redirect(url_for('index'))


@app.route('/crear_convocatoria', methods=['POST'])
def crear_convocatoria():
  if 'user_id' in session and session['nivel'] == 2:
    fecha = request.form['fecha']
    horas = request.form['horas']
    descripcion = request.form['descripcion']
    cupos = request.form['cupos']

    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO convocatorias (fecha, horas, descripcion, cupos,'
        ' creado_por) VALUES (?, ?, ?, ?, ?)',
        (fecha, horas, descripcion, cupos, session['user_id']),
    )
    conn.commit()
    conn.close()
    flash(
        f'Convocatoria creada con éxito para el día {fecha} ({horas} hrs).',
        'success',
    )

  return redirect(url_for('index'))


@app.route('/postular/<int:conv_id>')
def postular(conv_id):
  if 'user_id' in session and session['nivel'] == 1:
    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()

    cursor.execute('SELECT fecha FROM convocatorias WHERE id = ?', (conv_id,))
    conv_data = cursor.fetchone()
    fecha_turno = conv_data[0]

    cursor.execute(
        'SELECT username, nombre, apellido FROM usuarios WHERE id = ?',
        (session['user_id'],),
    )
    user_data = cursor.fetchone()
    username = user_data[0]
    nombre = user_data[1]
    apellido = user_data[2]

    porcentaje = verificar_franco_en_excel(username, nombre, apellido, fecha_turno)

    cursor.execute(
        'SELECT cupos, (SELECT COUNT(*) FROM postulaciones WHERE convocatoria_id = ?)'
        ' FROM convocatorias WHERE id = ?',
        (conv_id, conv_id),
    )
    data = cursor.fetchone()
    if data:
      max_cupos = data[0]
      inscriptos = data[1]

      cursor.execute(
          'SELECT * FROM postulaciones WHERE convocatoria_id = ? AND'
          ' usuario_id = ?',
          (conv_id, session['user_id']),
      )
      ya_postulado = cursor.fetchone()

      if not ya_postulado and inscriptos < max_cupos:
        cursor.execute(
            'INSERT INTO postulaciones (convocatoria_id, usuario_id, porcentaje)'
            ' VALUES (?, ?, ?)',
            (conv_id, session['user_id'], porcentaje),
        )
        conn.commit()
        flash(
            f'¡Te has postulado con éxito! (Calculado al {porcentaje}%).',
            'success',
        )
      else:
        flash(
            'No se pudo completar la postulación (cupo lleno o ya inscripto).',
            'warning',
        )

    conn.close()
  return redirect(url_for('index'))


@app.route('/cambiar_estado/<int:post_id>/<estado>')
def cambiar_estado(post_id, estado):
  if 'user_id' in session and session['nivel'] == 3:
    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE postulaciones SET estado = ?, aprobado_por = ? WHERE id = ?',
        (estado, session['user_id'], post_id),
    )
    conn.commit()
    conn.close()
    flash(f'Postulación marcada como: {estado}.', 'success')
  return redirect(url_for('index'))


@app.route('/eliminar_convocatoria/<int:conv_id>')
def eliminar_convocatoria(conv_id):
  if 'user_id' in session and session['nivel'] >= 2:
    conn = sqlite3.connect('horas_extras.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM postulaciones WHERE convocatoria_id = ?', (conv_id,))
    cursor.execute('DELETE FROM convocatorias WHERE id = ?', (conv_id,))
    conn.commit()
    conn.close()
    flash('Convocatoria eliminada correctamente.', 'warning')
  return redirect(url_for('index'))


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000, debug=True)