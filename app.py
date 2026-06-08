import sqlite3
import os
import pandas as pd
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.secret_key = "cardenal_master_key_2026"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
DB_NAME = "cardenal_napoles.db"

# ------------------------------------------------------------
# 1. INICIALIZACIÓN DE BASE DE DATOS
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, rol TEXT, sucursal TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS prestamos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nomina TEXT, empleado TEXT NOT NULL,
        area TEXT, monto_inicial REAL, saldo_pendiente REAL, fecha_otorgamiento TEXT, sucursal TEXT)''')
    
    try: cursor.execute('ALTER TABLE prestamos ADD COLUMN semana_otorgada INTEGER')
    except: pass
    try: cursor.execute('ALTER TABLE prestamos ADD COLUMN autoriza TEXT')
    except: pass
    try: cursor.execute('ALTER TABLE prestamos ADD COLUMN motivo_adicional TEXT')
    except: pass
    try: cursor.execute('ALTER TABLE prestamos ADD COLUMN id_empleado TEXT')
    except: pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, prestamo_id INTEGER, fecha TEXT, semana INTEGER, tipo TEXT, monto REAL,
        FOREIGN KEY(prestamo_id) REFERENCES prestamos(id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS cajas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sucursal TEXT UNIQUE, saldo_inicial REAL, saldo_actual REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_hora TEXT, usuario TEXT, accion TEXT,
        empleado_nombre TEXT, detalle TEXT, motivo TEXT, sucursal TEXT)''')
    
    sucursales = ['TACUBA', 'BOMBILLA', 'RESTORANES', 'NAPOLES', 'BRIGAR', 'BGARI']
    for s in sucursales:
        cursor.execute('INSERT OR IGNORE INTO cajas (sucursal, saldo_inicial, saldo_actual) VALUES (?, 0, 0)', (s,))
    
    admin_exist = cursor.execute('SELECT * FROM usuarios WHERE username="SISTEMAS"').fetchone()
    if not admin_exist:
        pw = generate_password_hash('admin123')
        cursor.execute('INSERT INTO usuarios (username, password, rol, sucursal) VALUES (?,?,?,?)', ('SISTEMAS', pw, 'ADMIN', 'TODAS'))
        
    conn.commit()
    conn.close()

def es_admin():
    return session.get('rol') == 'ADMIN'

# ------------------------------------------------------------
# FUNCIÓN PARA OBTENER PREFIJO DE 3 LETRAS POR SUCURSAL
# ------------------------------------------------------------
def obtener_prefijo_sucursal(sucursal):
    prefijos = {
        'TACUBA': 'TAC',
        'BRIGAR': 'BRI',
        'BOMBILLA': 'CDB',
        'RESTORANES': 'RIN',
        'NAPOLES': 'CNA',
        'BGARI': 'BGG'
    }
    return prefijos.get(sucursal.upper(), 'XXX')

# ------------------------------------------------------------
# FORMATEAR NÓMINA PARA ID (5 dígitos con ceros a la izquierda)
# ------------------------------------------------------------
def formatear_nomina_para_id(nomina):
    """
    Convierte la nómina a una cadena de 5 dígitos con ceros a la izquierda.
    Si la nómina contiene caracteres no numéricos, se devuelve tal cual.
    """
    nomina_str = str(nomina).strip()
    # Eliminar puntos, espacios y guiones
    nomina_limpia = re.sub(r'[.\- ]', '', nomina_str)
    # Verificar si es completamente numérico
    if nomina_limpia.isdigit():
        # Rellenar con ceros a la izquierda hasta 5 dígitos
        return nomina_limpia.zfill(5)
    else:
        # Si no es numérico, devolver como está (ej. A001)
        return nomina_limpia

# ------------------------------------------------------------
# GENERAR ID ÚNICO (PREFIJO + NÓMINA FORMATEADA A 5 DÍGITOS)
# ------------------------------------------------------------
def generar_id_empleado(sucursal, nomina, conn):
    prefijo = obtener_prefijo_sucursal(sucursal)
    nomina_formateada = formatear_nomina_para_id(nomina)
    base_id = f"{prefijo}{nomina_formateada}"
    cursor = conn.cursor()
    
    # Verificar si ya existe ese ID en la misma sucursal
    cursor.execute("SELECT id_empleado FROM prestamos WHERE sucursal = ? AND id_empleado = ?", (sucursal, base_id))
    if not cursor.fetchone():
        return base_id
    else:
        # Si ya existe, agregar un número correlativo _1, _2...
        contador = 1
        while True:
            nuevo_id = f"{base_id}_{contador}"
            cursor.execute("SELECT id_empleado FROM prestamos WHERE sucursal = ? AND id_empleado = ?", (sucursal, nuevo_id))
            if not cursor.fetchone():
                return nuevo_id
            contador += 1

# ------------------------------------------------------------
# 2. CONFIGURACIÓN DE FONDO
# ------------------------------------------------------------
@app.route('/configurar_fondo', methods=['POST'])
def configurar_fondo():
    if not es_admin():
        return redirect('/')
    sucursal = request.form.get('sucursal_caja')
    monto = float(request.form.get('monto_inicial'))
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.execute('UPDATE cajas SET saldo_inicial = ?, saldo_actual = ? WHERE sucursal = ?', (monto, monto, sucursal))
    conn.commit()
    conn.close()
    flash(f"Fondo de {sucursal} actualizado.", "success")
    return redirect('/')

# ------------------------------------------------------------
# 3. DASHBOARD MAESTRO
# ------------------------------------------------------------
@app.route('/')
def inicio():
    return redirect(f'/semana/{datetime.now().isocalendar()[1]}/sucursal/TODAS')

@app.route('/semana/<int:num_sem>/sucursal/<string:suc>')
def index(num_sem, suc):
    if 'user' not in session:
        return redirect('/login')
    if not es_admin():
        suc = session['sucursal']
        
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    todas_cajas = conn.execute('SELECT sucursal, saldo_inicial FROM cajas').fetchall()
    for caja in todas_cajas:
        deuda_total = conn.execute('SELECT SUM(saldo_pendiente) FROM prestamos WHERE sucursal = ?', (caja['sucursal'],)).fetchone()[0] or 0
        saldo_real = caja['saldo_inicial'] - deuda_total
        conn.execute('UPDATE cajas SET saldo_actual = ? WHERE sucursal = ?', (saldo_real, caja['sucursal']))
    conn.commit()

    cajas = conn.execute('SELECT * FROM cajas').fetchall()
    res_anio = conn.execute('SELECT fecha_otorgamiento FROM prestamos ORDER BY id DESC LIMIT 1').fetchone()
    anio_act = str(datetime.now().year) 
    if res_anio and res_anio[0]:
        match = re.search(r'\d{4}', str(res_anio[0]))
        if match:
            anio_act = match.group()
    
    if suc == 'TODAS':
        stats = conn.execute('SELECT SUM(monto_inicial), SUM(saldo_pendiente) FROM prestamos').fetchone()
        fondo_inicial_total = conn.execute('SELECT SUM(saldo_inicial) FROM cajas').fetchone()[0] or 0
    else:
        stats = conn.execute('SELECT SUM(monto_inicial), SUM(saldo_pendiente) FROM prestamos WHERE sucursal = ?', (suc,)).fetchone()
        fondo_inicial_total = conn.execute('SELECT SUM(saldo_inicial) FROM cajas WHERE sucursal = ?', (suc,)).fetchone()[0] or 0

    saldo_global_historico = stats[1] or 0
    fondo_actual = fondo_inicial_total - saldo_global_historico

    q_rec = "SELECT SUM(m.monto) FROM movimientos m JOIN prestamos p ON m.prestamo_id = p.id WHERE m.semana = ? AND m.tipo = 'ABONO'"
    q_sal = "SELECT SUM(saldo_pendiente) FROM prestamos WHERE id IN (SELECT prestamo_id FROM movimientos WHERE semana = ?)"
    p_sem = [num_sem]
    
    if suc != 'TODAS':
        q_rec += " AND p.sucursal = ?"
        q_sal += " AND sucursal = ?"
        p_sem.append(suc)
        
    tot_rec = conn.execute(q_rec, p_sem).fetchone()[0] or 0
    tot_sal = conn.execute(q_sal, p_sem).fetchone()[0] or 0
    totales_semana = (tot_sal, tot_rec)

    usuarios_lista = conn.execute('SELECT * FROM usuarios WHERE username != "SISTEMAS"').fetchall() if es_admin() else []

    if suc == 'TODAS':
        query = '''SELECT p.*, 
                          IFNULL(p.semana_otorgada, strftime('%W', p.fecha_otorgamiento)) as semana_otorgamiento, 
                          (SELECT MAX(semana) FROM movimientos WHERE prestamo_id = p.id AND semana = ?) as ultima_semana, 
                          (SELECT SUM(monto) FROM movimientos WHERE prestamo_id = p.id AND semana = ? AND tipo = 'ABONO') as abono_semana 
                   FROM prestamos p'''
        params = [num_sem, num_sem]
    else:
        query = '''SELECT p.*, 
                          IFNULL(p.semana_otorgada, strftime('%W', p.fecha_otorgamiento)) as semana_otorgamiento, 
                          (SELECT MAX(semana) FROM movimientos WHERE prestamo_id = p.id AND semana = ?) as ultima_semana, 
                          (SELECT SUM(monto) FROM movimientos WHERE prestamo_id = p.id AND semana = ? AND tipo = 'ABONO') as abono_semana 
                   FROM prestamos p 
                   WHERE sucursal = ?'''
        params = [num_sem, num_sem, suc]
        
    empleados = conn.execute(query, params).fetchall()
    conn.close()
    
    semana_real = datetime.now().isocalendar()[1]
    
    return render_template('index.html',
                          empleados=empleados,
                          stats=stats,
                          totales_semana=totales_semana,
                          fondo_actual=fondo_actual,
                          fondo_inicial_total=fondo_inicial_total,
                          semana_act=num_sem,
                          suc_act=suc,
                          cajas=cajas,
                          anio_act=anio_act,
                          admin=es_admin(),
                          usuarios=usuarios_lista,
                          sucursal_usuario=session.get('sucursal', 'TODAS'),
                          datetime=datetime,
                          semana_real=semana_real)

# ------------------------------------------------------------
# EDICIÓN DIRECTA DE PRÉSTAMOS (con regeneración de ID y redondeo)
# ------------------------------------------------------------
@app.route('/editar_prestamo_maestro', methods=['POST'])
def editar_prestamo_maestro():
    if not es_admin():
        return redirect('/')
    
    p_id = request.form.get('prestamo_id')
    nueva_nomina = request.form.get('nomina')
    nuevo_nombre = request.form.get('empleado')
    nueva_area = request.form.get('area')
    nuevo_monto = float(request.form.get('monto_inicial'))
    nuevo_autoriza = request.form.get('autoriza')

    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    
    viejo = cursor.execute('SELECT * FROM prestamos WHERE id = ?', (p_id,)).fetchone()
    if not viejo:
        conn.close()
        flash("Préstamo no encontrado.", "danger")
        return redirect(request.referrer or '/')

    monto_viejo = viejo[4]
    sucursal = viejo[7]
    id_actual = viejo[9] if len(viejo) > 9 else None
    diferencia = nuevo_monto - monto_viejo

    # Calcular el ID esperado según la sucursal y la nueva nómina
    prefijo_esperado = obtener_prefijo_sucursal(sucursal)
    nomina_formateada = formatear_nomina_para_id(nueva_nomina)
    id_esperado = f"{prefijo_esperado}{nomina_formateada}"
    
    # Decidir si mantener o regenerar el ID
    if not id_actual or id_actual.strip() == '' or id_actual == 'N/A' or id_actual == 'ENLACE' or not id_actual.startswith(prefijo_esperado):
        nuevo_id = generar_id_empleado(sucursal, nueva_nomina, conn)
    else:
        nuevo_id = id_actual

    # Actualizar todos los campos con redondeo en saldo_pendiente
    cursor.execute('''UPDATE prestamos 
                      SET nomina=?, empleado=?, area=?, monto_inicial=?, 
                          saldo_pendiente = round(saldo_pendiente + ?, 2), 
                          autoriza=?, id_empleado=?
                      WHERE id=?''',
                   (nueva_nomina, nuevo_nombre, nueva_area, nuevo_monto, diferencia, nuevo_autoriza, nuevo_id, p_id))
    
    cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual - ? WHERE sucursal = ?', (diferencia, sucursal))
    
    cursor.execute('INSERT INTO auditoria (fecha_hora, usuario, accion, empleado_nombre, detalle, motivo, sucursal) VALUES (?,?,?,?,?,?,?)',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('user', 'SISTEMAS'), 'EDICIÓN DATOS', nuevo_nombre,
                    f"Cambio datos maestros. Monto modificado de ${monto_viejo} a ${nuevo_monto}. ID asignado: {nuevo_id}", "Edición desde Panel de Control", sucursal))
    
    conn.commit()
    conn.close()
    flash("Datos del préstamo actualizados y ID generado automáticamente.", "success")
    return redirect(request.referrer or '/')

# ------------------------------------------------------------
# 4. ABONOS Y AUDITORÍA (con redondeo)
# ------------------------------------------------------------
@app.route('/registrar_abono', methods=['POST'])
def registrar_abono():
    if 'user' not in session:
        return redirect('/login')
    
    semana = request.form.get('semana_act')
    if not semana:
        semana = datetime.now().isocalendar()[1]
        
    ids_empleados = request.form.getlist('seleccionar_empleado')
    
    sucursal_actual = request.form.get("sucursal_act", "TODAS")
    if not sucursal_actual:
        sucursal_actual = "TODAS"
    
    if not ids_empleados:
        flash("Debes seleccionar empleados para procesar abonos.", "danger")
        return redirect(f'/semana/{semana}/sucursal/{sucursal_actual}')

    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    for emp_id in ids_empleados:
        monto_str = request.form.get(f'monto_abono_{emp_id}')
        if monto_str and float(monto_str) > 0:
            monto = float(monto_str)
            cursor.execute('INSERT INTO movimientos (prestamo_id, fecha, semana, tipo, monto) VALUES (?,?,?,?,?)',
                          (emp_id, fecha_hoy, semana, 'ABONO', monto))
            # Aplicar redondeo a 2 decimales
            cursor.execute('UPDATE prestamos SET saldo_pendiente = round(saldo_pendiente - ?, 2) WHERE id = ?', (monto, emp_id))
            cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual + ? WHERE sucursal = (SELECT sucursal FROM prestamos WHERE id = ?)',
                          (monto, emp_id))
            suc_res = cursor.execute('SELECT sucursal FROM prestamos WHERE id = ?', (emp_id,)).fetchone()
            if suc_res:
                sucursal_actual = suc_res[0]
            
    conn.commit()
    conn.close()
    flash("Abonos procesados correctamente.", "success")
    return redirect(f'/semana/{semana}/sucursal/{sucursal_actual}')

@app.route('/eliminar_empleado/<int:id>')
def eliminar_empleado(id):
    if not es_admin():
        return redirect('/')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.execute('DELETE FROM movimientos WHERE prestamo_id = ?', (id,))
    conn.execute('DELETE FROM prestamos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash("Trabajador eliminado del sistema.", "success")
    return redirect(request.referrer or '/')

@app.route('/auditar_abonos/<int:prestamo_id>')
def auditar_abonos(prestamo_id):
    if 'user' not in session:
        return redirect('/login')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    emp = conn.execute('SELECT * FROM prestamos WHERE id = ?', (prestamo_id,)).fetchone()
    
    if not es_admin() and emp['sucursal'] != session['sucursal']:
        conn.close()
        flash("Acceso denegado.", "danger")
        return redirect('/')
        
    movs = conn.execute('SELECT * FROM movimientos WHERE prestamo_id = ? ORDER BY semana DESC, id DESC', (prestamo_id,)).fetchall()
    conn.close()
    return render_template('editar_abonos.html', emp=emp, movimientos=movs, admin=es_admin())

@app.route('/actualizar_movimiento', methods=['POST'])
def actualizar_movimiento():
    if not es_admin():
        return redirect('/')
    mov_id = request.form['mov_id']
    prestamo_id = request.form['prestamo_id']
    nuevo_monto = float(request.form['nuevo_monto'])
    nueva_semana = request.form['nueva_semana']
    motivo = request.form['motivo'] 

    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    emp = cursor.execute('SELECT empleado, sucursal FROM prestamos WHERE id = ?', (prestamo_id,)).fetchone()
    mov_viejo = cursor.execute('SELECT monto FROM movimientos WHERE id = ?', (mov_id,)).fetchone()
    monto_viejo = mov_viejo[0] if mov_viejo else 0
    diferencia = nuevo_monto - monto_viejo

    cursor.execute('UPDATE movimientos SET monto = ?, semana = ? WHERE id = ?', (nuevo_monto, nueva_semana, mov_id))
    # Redondeo aplicado
    cursor.execute('UPDATE prestamos SET saldo_pendiente = round(saldo_pendiente - ?, 2) WHERE id = ?', (diferencia, prestamo_id))
    cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual + ? WHERE sucursal = (SELECT sucursal FROM prestamos WHERE id = ?)', (diferencia, prestamo_id))
    
    cursor.execute('INSERT INTO auditoria (fecha_hora, usuario, accion, empleado_nombre, detalle, motivo, sucursal) VALUES (?,?,?,?,?,?,?)',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('user', 'SISTEMAS'), 'EDICIÓN', emp[0],
                    f"Monto modificado: De ${monto_viejo} a ${nuevo_monto}", motivo, emp[1]))

    conn.commit()
    conn.close()
    flash("Movimiento corregido y documentado en bitácora.", "success")
    return redirect(f'/auditar_abonos/{prestamo_id}')

@app.route('/borrar_movimiento', methods=['POST'])
def borrar_movimiento():
    if not es_admin():
        return redirect('/')
    mov_id = request.form['mov_id']
    prestamo_id = request.form['prestamo_id']
    motivo = request.form['motivo'] 

    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    emp = cursor.execute('SELECT empleado, sucursal FROM prestamos WHERE id = ?', (prestamo_id,)).fetchone()
    mov_viejo = cursor.execute('SELECT monto, semana FROM movimientos WHERE id = ?', (mov_id,)).fetchone()
    
    if mov_viejo:
        monto_viejo = mov_viejo[0]
        semana = mov_viejo[1]
        # Redondeo aplicado
        cursor.execute('UPDATE prestamos SET saldo_pendiente = round(saldo_pendiente + ?, 2) WHERE id = ?', (monto_viejo, prestamo_id))
        cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual - ? WHERE sucursal = (SELECT sucursal FROM prestamos WHERE id = ?)', (monto_viejo, prestamo_id))
        cursor.execute('DELETE FROM movimientos WHERE id = ?', (mov_id,))
        
        cursor.execute('INSERT INTO auditoria (fecha_hora, usuario, accion, empleado_nombre, detalle, motivo, sucursal) VALUES (?,?,?,?,?,?,?)',
                       (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('user', 'SISTEMAS'), 'ELIMINACIÓN', emp[0],
                        f"Se eliminó abono de ${monto_viejo} (Semana {semana})", motivo, emp[1]))

    conn.commit()
    conn.close()
    flash("Abono eliminado y documentado en bitácora.", "warning")
    return redirect(f'/auditar_abonos/{prestamo_id}')

# ------------------------------------------------------------
# 5. REPORTES
# ------------------------------------------------------------
@app.route('/reporte/avanzado', methods=['POST'])
def r_avanzado():
    if 'user' not in session:
        return redirect('/login')
    
    tipo_reporte = request.form.get('tipo_reporte')
    f_inicio = request.form.get('fecha_inicio')
    f_fin = request.form.get('fecha_fin')
    suc = request.form.get('sucursal') if es_admin() else session['sucursal']
    
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    query = "SELECT *, (SELECT IFNULL(SUM(monto), 0) FROM movimientos WHERE prestamo_id = p.id AND tipo = 'ABONO') as total_abonado FROM prestamos p WHERE fecha_otorgamiento BETWEEN ? AND ?"
    params = [f_inicio, f_fin]

    if suc != 'TODAS':
        query += " AND sucursal = ?"
        params.append(suc)

    if tipo_reporte == 'solo_deudores':
        query += " AND saldo_pendiente > 0"
        titulo = "Reporte de Empleados con Adeudo"
    elif tipo_reporte == 'multi_prestamo':
        query += " AND nomina IN (SELECT nomina FROM prestamos GROUP BY nomina HAVING COUNT(*) > 1)"
        titulo = "Reporte de Empleados con Más de 1 Préstamo"
    else:
        titulo = "Reporte Histórico Filtrado"

    prestamos = conn.execute(query + " ORDER BY sucursal ASC, empleado ASC", params).fetchall()
    
    tot_inicial = sum(p['monto_inicial'] for p in prestamos)
    tot_pendiente = sum(p['saldo_pendiente'] for p in prestamos)
    tot_recuperado = sum(p['total_abonado'] for p in prestamos)
    conn.close()
    
    return render_template('reporte_especial.html',
                          prestamos=prestamos,
                          sucursal=suc,
                          tot_inicial=tot_inicial,
                          tot_pendiente=tot_pendiente,
                          tot_recuperado=tot_recuperado,
                          titulo=titulo,
                          f_inicio=f_inicio,
                          f_fin=f_fin)

@app.route('/reportes')
def reportes():
    if 'user' not in session:
        return redirect('/login')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    if es_admin():
        empleados = conn.execute('SELECT id, empleado, nomina, sucursal FROM prestamos ORDER BY sucursal ASC, empleado ASC').fetchall()
    else:
        empleados = conn.execute('SELECT id, empleado, nomina, sucursal FROM prestamos WHERE sucursal = ? ORDER BY empleado ASC', (session['sucursal'],)).fetchall()
    conn.close()
    return render_template('reportes.html', empleados=empleados, admin=es_admin(), suc_act=session.get('sucursal'))

@app.route('/reporte/historial_empresa', methods=['POST'])
def r_historial_empresa():
    if 'user' not in session:
        return redirect('/login')
    suc = request.form.get('sucursal') if es_admin() else session['sucursal']
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    query = '''
        SELECT p.*, 
        (SELECT IFNULL(SUM(monto), 0) FROM movimientos WHERE prestamo_id = p.id AND tipo = 'ABONO') as total_abonado
        FROM prestamos p
    '''
    
    if suc == 'TODAS' and es_admin():
        prestamos = conn.execute(query + ' ORDER BY sucursal ASC, empleado ASC').fetchall()
    else:
        prestamos = conn.execute(query + ' WHERE sucursal = ? ORDER BY empleado ASC', (suc,)).fetchall()
    
    tot_inicial = sum(p['monto_inicial'] for p in prestamos)
    tot_pendiente = sum(p['saldo_pendiente'] for p in prestamos)
    tot_recuperado = sum(p['total_abonado'] for p in prestamos)
    conn.close()
    
    return render_template('reporte_historial.html',
                          prestamos=prestamos,
                          sucursal=suc,
                          tot_inicial=tot_inicial,
                          tot_pendiente=tot_pendiente,
                          tot_recuperado=tot_recuperado)

@app.route('/reporte/kardex_empleado', methods=['POST'])
def r_kardex_emp():
    emp_id = request.form.get('empleado_id')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    emp = conn.execute('SELECT * FROM prestamos WHERE id = ?', (emp_id,)).fetchone()
    movs = conn.execute('SELECT * FROM movimientos WHERE prestamo_id = ? ORDER BY semana DESC', (emp_id,)).fetchall()
    conn.close()
    return render_template('kardex_detalle.html', emp=emp, movimientos=movs)

@app.route('/reporte/kardex_semana', methods=['POST'])
def r_kardex_sem():
    try:
        sem = int(request.form.get('semana'))
    except:
        sem = int(datetime.now().isocalendar()[1])
        
    suc = request.form.get('sucursal') if es_admin() else session['sucursal']
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    if suc == 'TODAS' and es_admin():
        prestamos = conn.execute('''
            SELECT p.* FROM prestamos p 
            WHERE CAST(IFNULL(p.semana_otorgada, strftime('%W', p.fecha_otorgamiento)) AS INTEGER) = ? 
            OR EXISTS (SELECT 1 FROM movimientos m WHERE m.prestamo_id = p.id AND CAST(m.semana AS INTEGER) = ?) 
            ORDER BY p.sucursal ASC, p.empleado ASC''', (sem, sem)).fetchall()
    else:
        prestamos = conn.execute('''
            SELECT p.* FROM prestamos p 
            WHERE (CAST(IFNULL(p.semana_otorgada, strftime('%W', p.fecha_otorgamiento)) AS INTEGER) = ? 
            OR EXISTS (SELECT 1 FROM movimientos m WHERE m.prestamo_id = p.id AND CAST(m.semana AS INTEGER) = ?)) 
            AND p.sucursal = ? 
            ORDER BY p.empleado ASC''', (sem, sem, suc)).fetchall()
    
    data = []
    for p in prestamos:
        movs = conn.execute('SELECT * FROM movimientos WHERE prestamo_id = ? ORDER BY semana DESC', (p['id'],)).fetchall()
        data.append({'emp': p, 'movimientos': movs})
        
    conn.close()
    return render_template('kardex_semana.html', data=data, semana=sem, sucursal=suc)

@app.route('/reporte/auditoria', methods=['POST', 'GET'])
def r_auditoria():
    if not es_admin():
        return redirect('/')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    registros = conn.execute('SELECT * FROM auditoria ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('reporte_auditoria.html', registros=registros)

# ------------------------------------------------------------
# 6. GESTIÓN DE USUARIOS
# ------------------------------------------------------------
@app.route('/editar_usuario', methods=['POST'])
def editar_usuario():
    if not es_admin():
        return redirect('/')
    u_id, u_name, u_suc, new_pass = request.form['id'], request.form['username'], request.form['sucursal'], request.form['password']
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    if new_pass:
        pw = generate_password_hash(new_pass)
        conn.execute('UPDATE usuarios SET username=?, password=?, sucursal=? WHERE id=?', (u_name, pw, u_suc, u_id))
    else:
        conn.execute('UPDATE usuarios SET username=?, sucursal=? WHERE id=?', (u_name, u_suc, u_id))
    conn.commit()
    conn.close()
    flash("Usuario actualizado.", "success")
    return redirect('/')

@app.route('/eliminar_usuario/<int:id>')
def eliminar_usuario(id):
    if not es_admin():
        return redirect('/')
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.execute('DELETE FROM usuarios WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash("Usuario eliminado.", "success")
    return redirect('/')

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    if not es_admin():
        return redirect('/')
    u, p, s = request.form['username'], generate_password_hash(request.form['password']), request.form['sucursal']
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    try:
        conn.execute('INSERT INTO usuarios (username, password, rol, sucursal) VALUES (?,?,?,?)', (u, p, 'SUCURSAL', s))
        conn.commit()
        flash("Usuario creado.", "success")
    except:
        flash("Error: El usuario ya existe.", "danger")
    conn.close()
    return redirect('/')

# ------------------------------------------------------------
# 7. TRASPASO ANUAL
# ------------------------------------------------------------
@app.route('/cambiar_anio', methods=['POST'])
def cambiar_anio():
    if not es_admin():
        return redirect('/')
    nuevo_anio = request.form['nuevo_anio']
    
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    prestamos_deuda = cursor.execute('SELECT * FROM prestamos WHERE saldo_pendiente > 0').fetchall()
    for p in prestamos_deuda:
        nuevo_id = generar_id_empleado(p['sucursal'], p['nomina'], conn)
        cursor.execute('''INSERT INTO prestamos (nomina, empleado, area, monto_inicial, saldo_pendiente, fecha_otorgamiento, sucursal, semana_otorgada, id_empleado) 
                          VALUES (?,?,?,?,?,?,?,?,?)''',
                       (p['nomina'], p['empleado'], p['area'], p['saldo_pendiente'], p['saldo_pendiente'],
                        f"{nuevo_anio}-01-01", p['sucursal'], 1, nuevo_id))
        cursor.execute('UPDATE prestamos SET saldo_pendiente = 0 WHERE id = ?', (p['id'],))
    conn.commit()
    conn.close()
    flash("Traspaso completado.", "success")
    return redirect('/')

# ------------------------------------------------------------
# 8. IMPORTACIÓN Y NUEVO PRÉSTAMO
# ------------------------------------------------------------
@app.route('/importar_excel', methods=['POST'])
def importar_excel():
    if not es_admin():
        return redirect('/')
    file = request.files['archivo_excel']
    suc_dest = request.form['sucursal_importacion']
    if file:
        try:
            df = pd.read_csv(file, encoding='latin1') if file.filename.endswith('.csv') else pd.read_excel(file)
            df.columns = [str(c).upper().strip() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()]
            
            conn = sqlite3.connect(DB_NAME, timeout=10.0)
            cursor = conn.cursor()
            for _, row in df.iterrows():
                nombre = row.get('NOMBRE', row.get('EMPLEADO', None))
                if pd.isna(nombre) or str(nombre).strip() == '':
                    continue
                
                nomina = str(row.get('N.NO', row.get('NOMINA', 'S/N'))).replace('.0', '')
                area = str(row.get('AREA', 'GENERAL'))
                
                monto_raw = str(row.get('MONTO', row.get('PRESTAMO', 0)))
                monto_limpio = re.sub(r'[^\d.]', '', monto_raw)
                monto = float(monto_limpio) if monto_limpio else 0.0
                
                fecha_raw = row.get('FECHA')
                if pd.isna(fecha_raw) or str(fecha_raw).strip() == '':
                    fecha = datetime.now().strftime('%Y-%m-%d')
                else:
                    fecha_str = str(fecha_raw).strip()
                    try:
                        fecha = datetime.strptime(fecha_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                    except:
                        fecha = fecha_str 

                sem_raw = row.get('SEM', row.get('SEMANA', None))
                if pd.notna(sem_raw) and str(sem_raw).strip() != '':
                    semana_otorgada = int(float(sem_raw))
                else:
                    try:
                        semana_otorgada = datetime.strptime(fecha, '%Y-%m-%d').isocalendar()[1]
                    except:
                        semana_otorgada = datetime.now().isocalendar()[1]
                
                id_empleado = generar_id_empleado(suc_dest, nomina, conn)
                        
                cursor.execute('''INSERT INTO prestamos 
                                  (nomina, empleado, area, monto_inicial, saldo_pendiente, fecha_otorgamiento, sucursal, semana_otorgada, id_empleado) 
                                  VALUES (?,?,?,?,?,?,?,?,?)''',
                               (nomina, nombre, area, monto, monto, fecha, suc_dest, semana_otorgada, id_empleado))
                cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual - ? WHERE sucursal = ?', (monto, suc_dest))
                
            conn.commit()
            conn.close()
            flash("Importación exitosa. Préstamos registrados.", "success")
        except Exception as e:
            print(f"Error importando archivo: {e}")
            flash("Error al leer el archivo. Verifica el formato.", "danger")
            
    return redirect('/')

@app.route('/nuevo_prestamo', methods=['POST'])
def nuevo_prestamo():
    if 'user' not in session:
        return redirect('/login')
    n = request.form['nomina']
    nom = request.form['nombre']
    a = request.form['area']
    m = float(request.form['monto'])
    f = request.form['fecha_otorgamiento']
    s = request.form['sucursal'] if es_admin() else session['sucursal']
    
    autoriza = request.form.get('autoriza', '')
    motivo = request.form.get('motivo', '')
    semana_otorgada = datetime.strptime(f, '%Y-%m-%d').isocalendar()[1]
    
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    cursor = conn.cursor()
    
    existente = cursor.execute('SELECT saldo_pendiente FROM prestamos WHERE nomina = ? AND saldo_pendiente > 0', (n,)).fetchone()
    if existente and existente[0] > 0 and str(motivo).strip() == '':
        flash(f"El empleado {nom} ya tiene un préstamo vigente de ${existente[0]}. Debes ingresar un MOTIVO obligatorio para agregarle otro.", "danger")
        conn.close()
        return redirect('/')
    
    id_empleado = generar_id_empleado(s, n, conn)
    
    cursor.execute('''INSERT INTO prestamos 
                      (nomina, empleado, area, monto_inicial, saldo_pendiente, fecha_otorgamiento, sucursal, semana_otorgada, autoriza, motivo_adicional, id_empleado) 
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                   (n, nom, a, m, m, f, s, semana_otorgada, autoriza, motivo, id_empleado))
    cursor.execute('UPDATE cajas SET saldo_actual = saldo_actual - ? WHERE sucursal = ?', (m, s))
    conn.commit()
    conn.close()
    flash(f"Préstamo registrado exitosamente con ID: {id_empleado}", "success")
    return redirect('/')

# ------------------------------------------------------------
# 9. API PARA AUTOCOMPLETADO (DESDE EXCEL)
# ------------------------------------------------------------
@app.route('/api/empleados_excel/<sucursal>')
def api_empleados_excel(sucursal):
    if 'user' not in session:
        return jsonify([])
    
    if sucursal == 'TODAS':
        return jsonify([])
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(base_dir, 'empleados')
    filepath = os.path.join(folder_path, f"{sucursal}.xlsx")
    if not os.path.exists(filepath):
        filepath = os.path.join(folder_path, f"{sucursal}.xls")
    if not os.path.exists(filepath):
        return jsonify([])

    try:
        df = pd.read_excel(filepath)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        col_nomina = next((c for c in df.columns if 'NOMINA' in c or 'NÓMINA' in c), None)
        col_nombre = next((c for c in df.columns if 'NOMBRE' in c or 'EMPLEADO' in c), None)

        if not col_nomina or not col_nombre:
            return jsonify([])

        df = df.dropna(subset=[col_nomina, col_nombre])
        
        empleados = []
        for _, row in df.iterrows():
            nomina = str(row[col_nomina]).replace('.0', '').strip()
            nombre = str(row[col_nombre]).strip()
            if nomina and nombre:
                empleados.append({'nomina': nomina, 'nombre': nombre})
            
        return jsonify(empleados)
    except Exception as e:
        print(f"Error leyendo excel {sucursal}: {e}")
        return jsonify([])

# ------------------------------------------------------------
# 10. GRÁFICAS POR SEDE
# ------------------------------------------------------------
@app.route('/graficas')
def graficas():
    if 'user' not in session:
        return redirect('/login')
    
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    if es_admin():
        sucursales = ['TACUBA', 'BOMBILLA', 'RESTORANES', 'NAPOLES', 'BRIGAR', 'BGARI']
        titulo = "Gráfica Global de Rendimiento (Todas las Sedes)"
    else:
        sucursales = [session['sucursal']]
        titulo = f"Gráfica de Rendimiento - {session['sucursal']}"
        
    labels, prestado, recuperado, pendiente = [], [], [], []
    for suc in sucursales:
        stats = conn.execute('SELECT SUM(monto_inicial) as prest, SUM(saldo_pendiente) as pend FROM prestamos WHERE sucursal = ?', (suc,)).fetchone()
        p = stats['prest'] or 0
        pd = stats['pend'] or 0
        r = p - pd
        labels.append(suc)
        prestado.append(p)
        recuperado.append(r)
        pendiente.append(pd)
    conn.close()
    
    return render_template('graficas.html',
                          labels=labels,
                          prestado=prestado,
                          recuperado=recuperado,
                          pendiente=pendiente,
                          admin=es_admin(),
                          titulo=titulo)

# ------------------------------------------------------------
# 11. ACCESO
# ------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        conn = sqlite3.connect(DB_NAME, timeout=10.0)
        conn.row_factory = sqlite3.Row
        user = conn.execute('SELECT * FROM usuarios WHERE username=?', (u,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], p):
            session['user'] = user['username']
            session['rol'] = user['rol']
            session['sucursal'] = user['sucursal']
            session.permanent = True
            return redirect('/')
        else:
            flash("Usuario o contraseña incorrectos.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    init_db()
    from waitress import serve
    print("=====================================================")
    print(" SERVIDOR EL CARDENAL INICIADO ")
    print(" Puerto: 5004")
    print("=====================================================")
    serve(app, host='0.0.0.0', port=5004)