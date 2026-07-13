import sqlite3
import shutil
import os

# Nombre de tu base de datos actual
DB_NAME = "cardenal_napoles.db"
# Nombre de la copia de seguridad que se va a crear
BACKUP_NAME = "cardenal_napoles_respaldo.db"

def limpiar_decimales():
    print("Iniciando proceso de limpieza de decimales...\n")

    # 1. Crear copia de seguridad por protección
    if os.path.exists(DB_NAME):
        shutil.copy(DB_NAME, BACKUP_NAME)
        print(f"[OK] Copia de seguridad creada exitosamente: {BACKUP_NAME}")
    else:
        print(f"[ERROR] No se encontró el archivo '{DB_NAME}' en esta carpeta.")
        print("Asegúrate de poner este script en la misma carpeta que tu base de datos.")
        return

    # 2. Conectar a la base de datos y limpiar
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Limpiar tabla de cajas
        print("[PROCESANDO] Redondeando saldos en tabla 'cajas'...")
        cursor.execute("UPDATE cajas SET saldo_inicial = ROUND(saldo_inicial), saldo_actual = ROUND(saldo_actual);")

        # Limpiar tabla de movimientos (abonos)
        print("[PROCESANDO] Redondeando montos en tabla 'movimientos'...")
        cursor.execute("UPDATE movimientos SET monto = ROUND(monto);")

        # Limpiar tabla de préstamos
        print("[PROCESANDO] Redondeando saldos en tabla 'prestamos'...")
        cursor.execute("UPDATE prestamos SET monto_inicial = ROUND(monto_inicial), saldo_pendiente = ROUND(saldo_pendiente);")

        # Guardar todos los cambios
        conn.commit()
        print("\n[¡ÉXITO!] La base de datos ha sido limpiada. Ya no existen decimales.")

    except sqlite3.Error as e:
        print(f"\n[ERROR] Ocurrió un problema al modificar la base de datos: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    limpiar_decimales()
    input("\nPresiona Enter para cerrar esta ventana...")