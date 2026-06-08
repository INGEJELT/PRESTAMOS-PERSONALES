import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("cardenal_napoles.db")
cursor = conn.cursor()

# 1. Tabla de Usuarios (Sucursales + SISTEMAS)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        rol TEXT, -- 'ADMIN' (SISTEMAS) o 'SUCURSAL'
        sucursal TEXT -- Nombre de la empresa asignada
    )
''')

# 2. Agregar columna sucursal a prestamos si no existe
try:
    cursor.execute("ALTER TABLE prestamos ADD COLUMN sucursal TEXT;")
except: pass

# 3. Crear usuario maestro SISTEMAS (Cambia 'admin123' por tu clave real)
password_hash = generate_password_hash('admin123')
cursor.execute("INSERT OR IGNORE INTO usuarios (username, password, rol, sucursal) VALUES (?, ?, ?, ?)",
               ('SISTEMAS', password_hash, 'ADMIN', 'TODAS'))

conn.commit()
conn.close()
print("✅ Sistema multi-sucursal configurado.")