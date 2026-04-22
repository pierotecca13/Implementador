"""Central configuration — sheet names, row offsets, hardcoded lookups."""

# ── Excel structure ──────────────────────────────────────────────────────────
HEADER_ROW = 9       # 1-based row index where column headers live
DATA_START_ROW = 10  # 1-based row index where data begins

# Sheet names exactly as they appear in the workbook
SHEET_REGISTRO          = "Formulario de Registro"
SHEET_PRODUCTOS         = "Formulario de Productos"
SHEET_PROVEEDORES       = "Formulario Proveedores Clientes"
SHEET_USUARIOS          = "Formulario de Usuarios"
SHEET_PARAMETROS        = "Parámetros"

SHEET_IMPRESORAS     = "Formulario de Impresoras"
SHEET_STOCK          = "Formulario de Stock"
SHEET_PERFIL_PERMISO = "Perfil Permiso"

# Filas por batch en bulk inserts (etiqueta / item / log_estado)
STOCK_CHUNK_SIZE = 5_000

SHEETS_TO_IGNORE = {
    "Formulario Distribuidora",
    "Formulario Droguería",
    "Formulario Etiqueta",
}

# Maps the normalised (uppercase, no accents) "Nombre de Impresora" value to
# fixed DB fields and the configuracion rows that must be updated for that type.
PRINTER_TYPE_MAP: dict[str, dict] = {
    "IMPRESORA ITEM": {
        "print_max": "1500",
        "tipo": "item",
        "genera_packs": 0,
        "genera_pallets": 0,
        "linea_produccion": 0,
        "id_pattern": 1,
        "plugin": "BDevService",
        "klass": "xml-zpl",
        "host_from_excel": True,
        "configuracion_updates": [
            ("PRINTER_ITEM_PLUGIN", "xml-zpl"),
            ("PRINTER_ITEM_NAME", "ITEM"),
        ],
    },
    "IMPRESORA AGRUPACION": {
        "print_max": "1500",
        "tipo": "pack",
        "genera_packs": 1,
        "genera_pallets": 1,
        "linea_produccion": 1,
        "id_pattern": 1,
        "plugin": "BDevService",
        "klass": "x-verifarmabrowserplugin",
        "host_from_excel": True,
        "configuracion_updates": [
            ("PRINTER_LOGI_PACK_PLUGIN", "BdevService"),
            ("PRINTER_LOGI_PACK_NAME", "AGRUPACION"),
            ("PRINTER_LOGI_PALLET_PLUGIN", "BdevService"),
            ("PRINTER_LOGI_PALLET_NAME", "AGRUPACION"),
        ],
    },
    "LIXIS": {
        "print_max": "150000",
        "tipo": "item",
        "genera_packs": 1,
        "genera_pallets": 1,
        "linea_produccion": 1,
        "id_pattern": 0,
        "plugin": "BDevService",
        "klass": "xml",
        "host_from_excel": True,
        "configuracion_updates": [],
    },
    "ONELITE": {
        "print_max": "150000",
        "tipo": "pack",
        "genera_packs": 1,
        "genera_pallets": 1,
        "linea_produccion": 0,
        "id_pattern": 0,
        "plugin": "BDevService",
        "klass": "xml",
        "host_from_excel": False,   # host=NULL — Onelite no usa conexión IP directa
        "configuracion_updates": [],
    },
}

# ── Empresa lookup ────────────────────────────────────────────────────────────
EMPRESA_LOOKUP: dict[str, int] = {
    "LABORATORIO": 1,
    "DISTRIBUIDORA": 2,
    "DROGUERIA": 3,
    "FARMACIA": 4,
    "ANMAT": 5,
    "CENTRAL": 6,
    "OPERADOR LOGISTICO": 7,
    "ESTABLECIMIENTO ASISTENCIAL": 8,
    "FINANCIADORA": 9,
    "LABORATORIO DE MEZCLA INTRAVENOSA": 10,
    "PACIENTE": 11,
    "ESTABLECIMIENTO ESTATAL": 12,
    "BOTIQUIN DE FARMACIA": 13,
    "PAIS": 14,
    "NO DEFINIDO": 15,
    "OPERADOR GENERAL": 16,
    "TR": 17,
}

# ── Parámetros especiales — el valor se envuelve en comillas simples ──────────
SPECIAL_QUOTED_PARAMS: set[str] = {
    "PRINTER_ITEM_PLUGIN",
    "PRINTER_ITEM_NAME",
    "PRINTER_LOGI_PACK_PLUGIN",
    "PRINTER_LOGI_PACK_NAME",
    "PRINTER_LOGI_PALLET_PLUGIN",
    "PRINTER_LOGI_PALLET_NAME",
    "SSCC_COMPANY_PREFFIX",
    "SERIAL_PREFFIX_COMPANY",
}

# ── Perfiles hardcodeados — siempre se insertan antes de los usuarios ─────────
# Estos IDs son fijos en todas las instalaciones del sistema
PERFILES_HARDCODE: list[dict] = [
    {"ID_PERFIL": 2, "NOMBRE": "Administrador"},
    {"ID_PERFIL": 3, "NOMBRE": "Calidad"},
    {"ID_PERFIL": 4, "NOMBRE": "Producción"},
    {"ID_PERFIL": 5, "NOMBRE": "Logística"},
]

# ── Contraseña por defecto cuando el campo se deja vacío ─────────────────────
DEFAULT_PASSWORD = "V3r1f4rm4"
