import sqlite3

DB_NAME = "cardenal_napoles.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Ver cuántos registros tienen saldos menores a 1 centavo (pero no exactamente cero)
cursor.execute("SELECT id, empleado, saldo_pendiente FROM prestamos WHERE ABS(saldo_pendiente) < 0.01 AND saldo_pendiente != 0")
problemas = cursor.fetchall()
print(f"Registros con saldo residual encontrados: {len(problemas)}")
for p in problemas:
    print(f"ID: {p[0]}, Empleado: {p[1]}, Saldo actual: {p[2]}")

# Corregir los saldos
cursor.execute("UPDATE prestamos SET saldo_pendiente = 0.0 WHERE ABS(saldo_pendiente) < 0.01")
conn.commit()
print(f"\nRegistros corregidos: {cursor.rowcount}")

conn.close()
print("Listo. Los saldos anómalos han sido puestos a cero.")