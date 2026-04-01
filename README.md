# implementador_masterdata

Herramienta CLI para importar datos de configuración desde un fichero Excel a una base de datos MySQL.

---

## Requisitos

- Python 3.10+
- MySQL 5.7+ / 8.x

## Instalación

```bash
# 1. Entrar a la carpeta del proyecto
cd implementador

# 2. Crear y activar un entorno virtual (recomendado)
python -m venv .venv

.venv\Scripts\activate        # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar credenciales de base de datos
cp .env.example .env
# Editar .env con los valores reales
```

## Configuración `.env`

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=tu_usuario
DB_PASSWORD=tu_contraseña
DB_NAME=nombre_base_de_datos
```

## Uso

Colocar el fichero Excel en la misma carpeta que `main.py` y ejecutar:

```bash
python main.py --file Formulario_Masterdata.xlsx
```

También se puede indicar la ruta completa al fichero:

```bash
python main.py --file C:\Users\usuario\Descargas\Formulario_Masterdata_v3.xlsx
```

## Pestañas procesadas

| Pestaña                        | Acción        | Tabla(s) MySQL               |
|--------------------------------|---------------|------------------------------|
| Formulario de Registro         | INSERT IGNORE | `eslabon`                    |
| Formulario de Productos        | INSERT IGNORE | `medicamento`                |
| Formulario Proveedores Clientes| INSERT IGNORE | `eslabon`, `eslabon_eslabon` |
| Parámetros                     | UPDATE        | `configuracion`              |

Las pestañas **Formulario Distribuidora**, **Formulario Droguería** y **Formulario Etiqueta** se ignoran silenciosamente.

## Estructura del proyecto

```
implementador_masterdata/
├── domain/
│   ├── models.py            # Dataclasses: Eslabon, Medicamento, EslabonEslabon, Parametro
│   └── interfaces.py        # Repositorios abstractos (ABC)
├── infrastructure/
│   ├── db_connection.py     # Conexión MySQL desde .env con python-dotenv
│   ├── excel_reader.py      # Lectura y parseo de las 4 pestañas
│   └── repositories.py      # Implementación INSERT IGNORE / UPDATE
├── application/
│   └── import_service.py    # Orquesta el flujo completo con transacción única
├── config/
│   └── settings.py          # Constantes: pestañas, lookup empresas, parámetros especiales
├── utils/
│   └── logger.py            # Logger a fichero (logs/import.log) + consola
├── logs/                    # Autocreada al ejecutar — almacena ficheros .log
├── main.py                  # CLI con argparse
├── requirements.txt
├── .env
├── .env.example
└── README.md
```

## Detalles técnicos

- **Fila de cabecera**: fila 9 en todas las pestañas. Los datos comienzan en la fila 10.
- **Filas vacías**: si la primera columna de una fila es `None`, se detiene el procesamiento de esa pestaña.
- **Fórmulas Excel**: `openpyxl` abre el fichero con `data_only=True` — se leen solo los valores calculados, nunca las fórmulas.
- **Detección dinámica de columnas**: la pestaña Parámetros detecta las columnas por nombre de cabecera (no por posición fija), tolerando variaciones de orden o columnas extra.
- **ID_LAB dinámico**: el `ID_LAB` de `medicamento` se resuelve consultando el `ID_ESLABON` real del laboratorio (`ID_EMPRESA = 1`) después de los inserts, evitando errores de FK silenciosos.
- **Relaciones eslabon_eslabon**: tras insertar todos los eslabones, se genera el producto cruzado entre eslabones con URL (Formulario de Registro) y sin URL (Formulario Proveedores Clientes), insertando una fila `TIPO='PR'` y otra `TIPO='CL'` por cada combinación.
- **Parámetros especiales**: los siguientes nombres se almacenan con el valor envuelto en comillas simples (ej: `'BDevService'`):
  - `PRINTER_ITEM_PLUGIN`, `PRINTER_ITEM_NAME`
  - `PRINTER_LOGI_PACK_PLUGIN`, `PRINTER_LOGI_PACK_NAME`
  - `PRINTER_LOGI_PALLET_PLUGIN`, `PRINTER_LOGI_PALLET_NAME`
  - `SSCC_COMPANY_PREFFIX`
- **Transacción única**: todos los pasos se ejecutan dentro de una sola transacción MySQL. Cualquier error provoca un `ROLLBACK` completo. Solo si todo es correcto se ejecuta `COMMIT`.

## Salida de ejemplo

```
============================================================
 RESUMEN DE IMPORTACIÓN
============================================================
 [Formulario de Registro            ]   2 filas |   2 OK |   0 errores
 [Formulario de Productos           ]  10 filas |  10 OK |   0 errores
 [Formulario Proveedores Clientes   ]   9 filas |   9 OK |   0 errores
 [eslabon_eslabon - relaciones      ]  36 filas |  36 OK |   0 errores
 [Parámetros                        ]  34 filas |  34 OK |   0 errores
------------------------------------------------------------
 RESULTADO: ✅ ÉXITO — COMMIT realizado
============================================================
```
