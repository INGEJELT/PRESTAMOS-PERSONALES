import sqlite3
conn = sqlite3.connect("cardenal_napoles.db")
try:
    conn.execute("ALTER TABLE prestamos ADD COLUMN area TEXT;")
    print("✅ Columna 'area' agregada con éxito.")
except:
    print("⚠️ La columna 'area' ya existía.")
conn.commit()
conn.close()