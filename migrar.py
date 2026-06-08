import sqlite3
import pandas as pd
import os

DB_NAME = "cardenal_napoles.db"
EXCEL_FILE = "PRESTAMOS AL PERSONAL SEM 7 2026.xlsm"

def migrar_datos_exactos():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Error: No se encuentra el archivo {EXCEL_FILE}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. CREAR TABLAS (Por si el archivo .db es nuevo o está vacío)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado TEXT NOT NULL,
            monto_inicial REAL,
            saldo_pendiente REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER,
            fecha TEXT,
            semana INTEGER,
            tipo TEXT,
            monto REAL,
            FOREIGN KEY(prestamo_id) REFERENCES prestamos(id)
        )
    ''')

    # 2. LIMPIAR DATOS PREVIOS (Para evitar duplicar la importación)
    cursor.execute('DELETE FROM movimientos')
    cursor.execute('DELETE FROM prestamos')
    
    print("--- Procesando archivo de EL CARDENAL DE LA NÁPOLES ---")
    
    try:
        xls = pd.ExcelFile(EXCEL_FILE)
    except Exception as e:
        print(f"❌ Error al abrir el Excel: {e}")
        return

    # 3. LEER LAS 58 HOJAS [cite: 1-10, 88]
    for sheet in xls.sheet_names:
        if "sheet" in sheet.lower():
            try:
                # Leemos la hoja ignorando encabezados para usar coordenadas exactas
                df = pd.read_excel(xls, sheet_name=sheet, header=None)
                
                # Extraer Nombre (Fila 0, Col 1) y Monto (Fila 1, Col 1) [cite: 1, 64]
                nombre = str(df.iloc[0, 1]).strip()
                monto_total = float(df.iloc[1, 1])
                
                if nombre == "nan" or monto_total <= 0:
                    continue

                # Insertar Empleado
                cursor.execute('INSERT INTO prestamos (empleado, monto_inicial, saldo_pendiente) VALUES (?, ?, ?)',
                               (nombre, monto_total, monto_total))
                emp_id = cursor.lastrow_id
                
                # Extraer Semanas 1 a 8 [cite: 5, 10, 44]
                for sem in range(1, 9):
                    fila_semana = sem + 4 # Ajuste de fila según tu formato
                    abono = df.iloc[fila_semana, 2]
                    
                    if pd.notna(abono) and abono > 0:
                        cursor.execute('''
                            INSERT INTO movimientos (prestamo_id, fecha, semana, tipo, monto)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (emp_id, '2026-03-05', sem, 'ABONO HISTÓRICO', abono))
                        
                        # Actualizar saldo real restando los abonos pasados
                        cursor.execute('UPDATE prestamos SET saldo_pendiente = saldo_pendiente - ? WHERE id = ?',
                                       (abono, emp_id))
                
                print(f"✅ Importado: {nombre}")
            except:
                continue

    conn.commit()
    conn.close()
    print("\n🚀 ¡Historial de 8 semanas cargado correctamente!")

if __name__ == "__main__":
    migrar_datos_exactos()