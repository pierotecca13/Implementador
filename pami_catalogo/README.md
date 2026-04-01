# Importador Catálogo PAMI

Script Python que descarga el catálogo de medicamentos trazables desde el portal de PAMI y lo importa a la base de datos del implementador (`eslabon` y `medicamento`).

---

## Qué hace

1. **Muestra un popup** para ingresar los datos de conexión a la base de datos.
2. **Descarga el catálogo** desde `https://trazabilidad.pami.org.ar/trazamed/consultaCatalogoByGTIN.tz` (archivo Excel con ~30.000 registros).
3. **Inserta en `eslabon`** (INSERT IGNORE) todos los laboratorios/distribuidores únicos encontrados por GLN/CUFE.
4. **Recupera los IDs** de los eslabones ya insertados o preexistentes.
5. **Inserta en `medicamento`** (INSERT IGNORE) vinculando cada GTIN a su eslabon correspondiente.

Los inserts usan `INSERT IGNORE` para ser idempotentes: ejecutar el script múltiples veces no genera duplicados.

---

## Mapeo de columnas

| Columna Excel | Campo DB            |
|---------------|---------------------|
| GTIN          | medicamento.BC_EAN_1 |
| DESCRIPCION   | medicamento.NOMBRE  |
| GLN/CUFE      | eslabon.GLN         |
| RAZON SOCIAL  | eslabon.RSOC        |
| CUIT          | eslabon.CUIT        |

### Valores fijos insertados

**eslabon:**
- `ID_EMPRESA = 1`
- `ACTIVO = 1`

**medicamento:**
- `ID_LAB` = ID del eslabon cuyo GLN coincide con el de esa fila
- `TRAZABLE = 1`
- `EXIGIBLE = 1`
- `ACTIVO = 1`
- `DOSIS = 1`
- `EN_LISTADO_ANMAT = 'Sin definir'`

---

## Requisitos

Las dependencias ya están en el `requirements.txt` del proyecto principal:

```
requests
openpyxl
mysql-connector-python
```

Si no están instaladas:

```bash
pip install requests openpyxl mysql-connector-python
```

---

## Cómo ejecutar

```bash
# Desde la raíz del proyecto (con el venv activado)
python pami_catalogo/importar_catalogo.py
```

Se abre una ventana donde debés completar:

| Campo         | Descripción                              |
|---------------|------------------------------------------|
| Host          | IP o hostname del servidor MySQL         |
| Puerto        | Puerto MySQL (por defecto 3306)          |
| Usuario       | Usuario de la base de datos              |
| Contraseña    | Contraseña del usuario                   |
| Base de datos | Nombre del schema (ej. `implementador`)  |

> **Nota:** Si la base de datos es remota (de empresa), asegurate de estar conectado a la VPN antes de ejecutar.

---

## Notas de rendimiento

- Los inserts se hacen en lotes de **500 registros** (`executemany`) para minimizar round-trips al servidor.
- La recuperación de IDs de eslabones también se pagina en lotes de 500.
- En una red local el proceso completo (~30.000 medicamentos + ~N eslabones) tarda aproximadamente 1-3 minutos dependiendo del servidor.
