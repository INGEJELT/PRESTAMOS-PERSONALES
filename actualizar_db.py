import sqlite3

def actualizar():
    conn = sqlite3.connect("cardenal_napoles.db")
    cursor = conn.cursor()
    
    # Intentamos agregar las columnas una por una
    columnas = [
        ("nomina", "TEXT"),
        ("fecha_otorgamiento", "TEXT")
    ]
    
    for nombre, tipo in columnas:
        try:
            cursor.execute(f"ALTER TABLE prestamos ADD COLUMN {nombre} {tipo};")
            print(f"✅ Columna '{nombre}' agregada con éxito.")
        except sqlite3.OperationalError:
            print(f"⚠️ La columna '{nombre}' ya existe o no se pudo agregar.")
            
    conn.commit()
    conn.close()
    print("\n🚀 Base de datos actualizada para El Cardenal.")

if __name__ == "__main__":
    actualizar()