import tkinter as tk
from tkinter import ttk, messagebox
import requests
import xlrd
import mysql.connector
from io import BytesIO
import re
import sys
import threading

BASE_URL    = "https://trazabilidad.pami.org.ar"
URL_PAGINA  = f"{BASE_URL}/trazamed/consultaCatalogoByGTIN.tz"
URL_AU      = f"{BASE_URL}/trazamed/zkau"
BATCH_SIZE  = 500


# ---------------------------------------------------------------------------
# Descarga y lectura del Excel
# ---------------------------------------------------------------------------

def descargar_excel():
    """
    Descarga el catálogo de PAMI simulando la interacción con el portal ZK:
    1. GET a la página para obtener sesión y desktop ID.
    2. POST al endpoint AU simulando el click en el botón 'Exportar'.
    3. GET al recurso CatalogoGtinExcel para descargar el archivo Excel.
    """
    http = requests.Session()
    http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    print("Conectando al portal PAMI...", flush=True)
    resp = http.get(URL_PAGINA, timeout=30)
    resp.raise_for_status()

    dt_match = re.search(r"dt:'(z_[a-zA-Z0-9]+)'", resp.text)
    if not dt_match:
        raise RuntimeError("No se pudo obtener el desktop ID del portal PAMI.")
    desktop_id = dt_match.group(1)
    jsessionid = http.cookies.get("JSESSIONID", "")

    print("Solicitando exportación del catálogo...", flush=True)
    au_url = f"{URL_AU};jsessionid={jsessionid}"
    au_resp = http.post(au_url, timeout=60, data={
        "dtid":   desktop_id,
        "cmd_0":  "onClick",
        "uuid_0": "zk_comp_51",
        "data_0": '{"x":1,"y":1,"which":1,"x0":0,"y0":0,"cntx":1,"cnty":1,"keys":0}',
    })
    au_resp.raise_for_status()

    excel_url = f"{BASE_URL}/trazamed/CatalogoGtinExcel;jsessionid={jsessionid}"
    print("Descargando archivo Excel...", flush=True)
    file_resp = http.get(excel_url, timeout=120)
    file_resp.raise_for_status()

    kb = len(file_resp.content) / 1024
    print(f"Descarga completada ({kb:.1f} KB)", flush=True)
    return BytesIO(file_resp.content)


def leer_excel(file_obj):
    print("Procesando archivo Excel (.xls)...", flush=True)
    wb = xlrd.open_workbook(file_contents=file_obj.read())
    ws = wb.sheet_by_index(0)

    headers = [str(ws.cell_value(0, c)).strip().upper() for c in range(ws.ncols)]

    filas = []
    for r in range(1, ws.nrows):
        row = [ws.cell_value(r, c) for c in range(ws.ncols)]
        if not any(row):
            continue
        filas.append(dict(zip(headers, row)))

    print(f"Total de filas leídas: {len(filas)}", flush=True)
    return filas


# ---------------------------------------------------------------------------
# Conexión a MySQL
# ---------------------------------------------------------------------------

def conectar_db(datos):
    print(f"Conectando a {datos['host']}:{datos['port']} / {datos['database']}...", flush=True)
    conn = mysql.connector.connect(
        host=datos["host"],
        port=int(datos["port"]),
        user=datos["user"],
        password=datos["password"],
        database=datos["database"],
        charset="utf8mb4",
        autocommit=False,
    )
    print("Conexión exitosa.", flush=True)
    return conn


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------

def importar(conn, filas):
    cursor = conn.cursor()

    # -- 1. Recopilar eslabones únicos por GLN --
    eslabones_map = {}
    for f in filas:
        gln = str(f.get("GLN/CUFE") or "").strip()
        if gln:
            eslabones_map[gln] = {
                "rsoc": str(f.get("RAZON SOCIAL") or "")[:150],
                "cuit": str(f.get("CUIT") or "")[:11],
            }

    glns = list(eslabones_map.keys())
    print(f"Eslabones únicos a procesar: {len(glns)}", flush=True)

    # -- 2. Consultar qué GLNs ya existen (activo=1) para no duplicar --
    print("Verificando eslabones existentes...", flush=True)
    gln_to_id = {}
    for i in range(0, len(glns), BATCH_SIZE):
        chunk = glns[i : i + BATCH_SIZE]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(
            f"SELECT ID_ESLABON, GLN FROM eslabon WHERE GLN IN ({placeholders}) AND ACTIVO = 1",
            chunk,
        )
        for id_eslabon, gln in cursor.fetchall():
            gln_to_id[str(gln)] = id_eslabon

    glns_nuevos = [g for g in glns if g not in gln_to_id]
    print(f"Eslabones ya existentes: {len(gln_to_id)}  |  A insertar: {len(glns_nuevos)}", flush=True)

    # -- 3. Insertar solo los GLNs que no existen todavía --
    if glns_nuevos:
        sql_eslabon = (
            "INSERT INTO eslabon (ID_EMPRESA, RSOC, GLN, CUIT, ACTIVO) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        eslabon_batch = [
            (1, eslabones_map[g]["rsoc"], g, eslabones_map[g]["cuit"], 1)
            for g in glns_nuevos
        ]

        insertados_eslabon = 0
        for i in range(0, len(eslabon_batch), BATCH_SIZE):
            chunk = eslabon_batch[i : i + BATCH_SIZE]
            cursor.executemany(sql_eslabon, chunk)
            conn.commit()
            insertados_eslabon += cursor.rowcount
            print(f"  Eslabones insertados: {min(i + BATCH_SIZE, len(eslabon_batch))}/{len(eslabon_batch)}", end="\r", flush=True)
        print(f"\nEslabones nuevos insertados: {insertados_eslabon}", flush=True)

        # Recuperar IDs de los recién insertados
        for i in range(0, len(glns_nuevos), BATCH_SIZE):
            chunk = glns_nuevos[i : i + BATCH_SIZE]
            placeholders = ",".join(["%s"] * len(chunk))
            cursor.execute(
                f"SELECT ID_ESLABON, GLN FROM eslabon WHERE GLN IN ({placeholders}) AND ACTIVO = 1",
                chunk,
            )
            for id_eslabon, gln in cursor.fetchall():
                gln_to_id[str(gln)] = id_eslabon

    print(f"Total IDs de eslabones disponibles: {len(gln_to_id)}", flush=True)

    # -- 4. Armar lote de medicamentos --
    sql_med = (
        "INSERT IGNORE INTO medicamento "
        "(ID_LAB, NOMBRE, BC_EAN_1, TRAZABLE, EXIGIBLE, ACTIVO, DOSIS, EN_LISTADO_ANMAT) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )

    med_batch = []
    omitidos = 0
    for f in filas:
        gtin_raw = str(f.get("GTIN/CÓDIGO DE PRODUCTO") or "").strip()
        gln      = str(f.get("GLN/CUFE") or "").strip()
        desc     = str(f.get("DESCRIPCION") or "")[:250]
        id_lab   = gln_to_id.get(gln)

        if not gtin_raw or not id_lab:
            omitidos += 1
            continue

        # Quitar solo el primer carácter si es '0' (de 14 a 13 dígitos)
        gtin = gtin_raw[1:] if gtin_raw.startswith("0") else gtin_raw

        med_batch.append((id_lab, desc, gtin, 1, 1, 1, 1, "Sin definir"))

    if omitidos:
        print(f"Filas omitidas (sin GTIN o sin eslabon asociado): {omitidos}", flush=True)
    print(f"Medicamentos a procesar: {len(med_batch)}", flush=True)

    # -- 5. INSERT IGNORE en medicamento en lotes --
    insertados_med = 0
    for i in range(0, len(med_batch), BATCH_SIZE):
        chunk = med_batch[i : i + BATCH_SIZE]
        cursor.executemany(sql_med, chunk)
        conn.commit()
        insertados_med += cursor.rowcount
        print(f"  Medicamentos procesados: {min(i + BATCH_SIZE, len(med_batch))}/{len(med_batch)}", end="\r", flush=True)

    print(f"\nMedicamentos insertados: {insertados_med}  (omitidos por duplicado: {len(med_batch) - insertados_med})", flush=True)
    cursor.close()
    return {"eslabones": len(glns_nuevos), "medicamentos": insertados_med}


# ---------------------------------------------------------------------------
# Main – ventana única que permanece abierta durante el proceso
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    root.title("Importar Catálogo PAMI")
    root.resizable(False, False)

    root.update_idletasks()
    w, h = 420, 340
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Widgets del formulario ──────────────────────────────────────────────
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text="Conexión a Base de Datos", font=("", 12, "bold")).grid(
        row=0, column=0, columnspan=2, pady=(0, 15)
    )

    campos = [
        ("Host:",          "host",     "localhost", False),
        ("Puerto:",        "port",     "3306",      False),
        ("Usuario:",       "user",     "",          False),
        ("Contraseña:",    "password", "",          True),
        ("Base de datos:", "database", "",          False),
    ]

    entries = {}
    for i, (label, key, default, secret) in enumerate(campos, start=1):
        ttk.Label(frame, text=label).grid(row=i, column=0, sticky="e", pady=5, padx=(0, 8))
        entry = ttk.Entry(frame, width=30, show="*" if secret else "")
        entry.insert(0, default)
        entry.grid(row=i, column=1, sticky="w", pady=5)
        entries[key] = entry

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=len(campos) + 1, column=0, columnspan=2, pady=(15, 0))
    btn_importar = ttk.Button(btn_frame, text="Conectar e Importar")
    btn_importar.pack(side=tk.LEFT, padx=5)
    btn_cancelar = ttk.Button(btn_frame, text="Cancelar")
    btn_cancelar.pack(side=tk.LEFT, padx=5)

    # Label de estado (oculto hasta que arranca el proceso)
    lbl_estado = ttk.Label(frame, text="", foreground="gray", wraplength=360, justify="center")
    lbl_estado.grid(row=len(campos) + 2, column=0, columnspan=2, pady=(12, 0))

    # ── Lógica ─────────────────────────────────────────────────────────────

    def set_procesando(procesando: bool):
        """Bloquea/desbloquea el formulario según si estamos procesando."""
        state = "disabled" if procesando else "normal"
        for entry in entries.values():
            entry.config(state=state)
        btn_importar.config(state=state)
        btn_cancelar.config(state=state)

    def actualizar_estado(texto: str):
        lbl_estado.config(text=texto)
        root.update_idletasks()

    def cancelar():
        root.destroy()
        sys.exit(0)

    def iniciar_importacion():
        datos = {key: entry.get().strip() for key, entry in entries.items()}
        if not all(datos.values()):
            messagebox.showwarning("Campos requeridos", "Todos los campos son obligatorios.", parent=root)
            return

        set_procesando(True)
        actualizar_estado("Iniciando proceso, por favor espere...")

        def tarea():
            try:
                root.after(0, lambda: actualizar_estado("Descargando catálogo desde PAMI..."))
                file_obj = descargar_excel()

                root.after(0, lambda: actualizar_estado("Procesando archivo Excel..."))
                filas = leer_excel(file_obj)

                root.after(0, lambda: actualizar_estado("Conectando a la base de datos..."))
                conn = conectar_db(datos)

                root.after(0, lambda: actualizar_estado(
                    f"Importando {len(filas):,} registros en la base de datos..."
                ))
                resultado = importar(conn, filas)
                conn.close()

                root.after(0, lambda r=resultado: finalizar_ok(r))
            except Exception as e:
                root.after(0, lambda err=e: finalizar_error(err))

        threading.Thread(target=tarea, daemon=True).start()

    def finalizar_ok(resultado):
        root.withdraw()
        eslabones_nuevos = resultado["eslabones"]
        meds_nuevos      = resultado["medicamentos"]

        if eslabones_nuevos == 0 and meds_nuevos == 0:
            messagebox.showinfo(
                "Sin novedades",
                "No hay nada para actualizar.\n"
                "Todos los registros del catálogo ya estaban cargados en la base de datos.",
            )
        else:
            messagebox.showinfo(
                "Importación completada",
                f"Catálogo PAMI importado correctamente.\n\n"
                f"  Medicamentos nuevos insertados : {meds_nuevos:,}\n"
                f"  Eslabones nuevos insertados    : {eslabones_nuevos:,}",
            )
        root.destroy()
        sys.exit(0)

    def finalizar_error(err):
        set_procesando(False)
        actualizar_estado("")
        messagebox.showerror("Error durante la importación", str(err), parent=root)

    btn_importar.config(command=iniciar_importacion)
    btn_cancelar.config(command=cancelar)
    root.protocol("WM_DELETE_WINDOW", cancelar)

    root.mainloop()


if __name__ == "__main__":
    main()
