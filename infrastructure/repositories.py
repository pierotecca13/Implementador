"""Concrete MySQL repository implementations."""
from typing import List, Optional
from mysql.connector import MySQLConnection

from domain.models import Eslabon, Medicamento, EslabonEslabon, Parametro, Perfil, Printer, Usuario
from config.settings import STOCK_CHUNK_SIZE
from domain.interfaces import (
    EslabonRepository,
    MedicamentoRepository,
    EslabonEslabonRepository,
    ConfiguracionRepository,
    PerfilRepository,
    PrinterRepository,
    UsuarioRepository,
)
from utils.logger import get_logger

logger = get_logger()


class MySQLEslabonRepository(EslabonRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def get_existing_glns(self) -> set:
        """Carga todos los GLN existentes en un set para chequeo en memoria."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT GLN FROM eslabon")
        glns = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return glns

    def insert(self, eslabon: Eslabon) -> None:
        sql = """
            INSERT INTO eslabon
                (ID_EMPRESA, RSOC, GLN, CUIT, USER_ANMAT, PASS_ANMAT, URL, DIRECCION, ACTIVO, IMAGEN)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        imagen = "dynamic" if eslabon.URL else None
        params = (
            eslabon.ID_EMPRESA,
            eslabon.RSOC,
            eslabon.GLN,
            eslabon.CUIT,
            eslabon.USER_ANMAT,
            eslabon.PASS_ANMAT,
            eslabon.URL,
            eslabon.DIRECCION,
            eslabon.ACTIVO,
            imagen,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cursor.close()

    def get_ids_with_url(self) -> List[int]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT ID_ESLABON FROM eslabon WHERE URL IS NOT NULL AND URL != ''")
        ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return ids

    def get_lab_id(self) -> int:
        """Return ID_ESLABON of the first LABORATORIO (ID_EMPRESA=1) in the table."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ID_ESLABON FROM eslabon WHERE ID_EMPRESA = 1 LIMIT 1"
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise ValueError(
                "No se encontró ningún eslabon con ID_EMPRESA=1 (LABORATORIO) en la base de datos. "
                "Verificar que el Formulario de Registro fue insertado correctamente."
            )
        return row[0]

    def get_ids_without_url(self) -> List[int]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT ID_ESLABON FROM eslabon WHERE URL IS NULL OR URL = ''")
        ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return ids

    def get_id_by_url(self, url: str) -> Optional[int]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ID_ESLABON FROM eslabon WHERE TRIM(URL) = TRIM(%s) LIMIT 1", (url,)
        )
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None

    def get_id_by_gln(self, gln: str) -> Optional[int]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ID_ESLABON FROM eslabon WHERE GLN = %s LIMIT 1", (gln,)
        )
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None


class MySQLMedicamentoRepository(MedicamentoRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def insert_ignore(self, med: Medicamento) -> bool:
        sql = """
            INSERT IGNORE INTO medicamento
                (ID_LAB, NOMBRE, BC_EAN_1, BC_EAN_2, ITEMS_POR_PACK,
                 PACKS_POR_PALLET, TRAZABLE, EXIGIBLE, ACTIVO, SERIE,
                 cantidad_capas_pack, level_aggregation)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            med.ID_LAB,
            med.NOMBRE,
            med.BC_EAN_1,
            med.BC_EAN_2,
            med.ITEMS_POR_PACK,
            med.PACKS_POR_PALLET,
            med.TRAZABLE,
            med.EXIGIBLE,
            med.ACTIVO,
            med.SERIE,
            med.CANTIDAD_CAPAS_PACK,
            med.LEVEL_AGGREGATION,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        inserted = cursor.rowcount > 0
        cursor.close()
        return inserted


class MySQLEslabonEslabonRepository(EslabonEslabonRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def get_existing_relations(self) -> set:
        """Carga todas las tuplas (ID_ESLABON, ID_RELACION, TIPO) existentes en un set."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT ID_ESLABON, ID_RELACION, TIPO FROM eslabon_eslabon")
        relations = {(row[0], row[1], row[2]) for row in cursor.fetchall()}
        cursor.close()
        return relations

    def insert(self, rel: EslabonEslabon) -> None:
        sql = """
            INSERT INTO eslabon_eslabon
                (ID_ESLABON, ID_RELACION, TIPO, ACTIVO, FECHA_ALTA)
            VALUES
                (%s, %s, %s, %s, %s)
        """
        params = (
            rel.ID_ESLABON,
            rel.ID_RELACION,
            rel.TIPO,
            rel.ACTIVO,
            rel.FECHA_ALTA,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cursor.close()


class MySQLConfiguracionRepository(ConfiguracionRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def update(self, parametro: Parametro) -> int:
        """
        UPDATE configuracion SET VALOR WHERE NOMBRE.

        Returns:
            1  — row found and updated (value changed)
            0  — row found but value was already the same (no change needed)
           -1  — row not found in configuracion
        """
        # First check if the row exists at all
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM configuracion WHERE TRIM(NOMBRE) = TRIM(%s)",
            (parametro.NOMBRE,)
        )
        exists = cursor.fetchone()[0] > 0
        cursor.close()

        if not exists:
            logger.info(
                f"  Parámetro '{parametro.NOMBRE}' no existe en esta instalación — omitido."
            )
            return -1

        # Row exists — run the update (rowcount may be 0 if value is unchanged)
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE configuracion SET VALOR = %s WHERE TRIM(NOMBRE) = TRIM(%s)",
            (parametro.VALOR, parametro.NOMBRE)
        )
        affected = cursor.rowcount
        cursor.close()
        return affected  # 1 = changed, 0 = existed but same value


class MySQLPerfilRepository(PerfilRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def insert_ignore(self, perfil: Perfil) -> bool:
        """INSERT IGNORE with explicit ID to guarantee fixed ID_PERFIL values."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT IGNORE INTO perfil (ID_PERFIL, NOMBRE) VALUES (%s, %s)",
            (perfil.ID_PERFIL, perfil.NOMBRE)
        )
        inserted = cursor.rowcount > 0
        cursor.close()
        return inserted

    def get_id_by_nombre(self, nombre: str) -> Optional[int]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ID_PERFIL FROM perfil WHERE TRIM(NOMBRE) = TRIM(%s) LIMIT 1", (nombre,)
        )
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None


class MySQLPrinterRepository(PrinterRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def get_existing_nombres(self) -> set:
        """Carga todos los nombres de printer existentes en un set para chequeo en memoria."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT nombre FROM printer")
        nombres = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return nombres

    def insert(self, printer: Printer) -> None:
        sql = """
            INSERT INTO printer
                (nombre, print_max, tipo, genera_packs, genera_pallets,
                 linea_produccion, id_pattern, plugin, class, activo,
                 id_category, state, HOST, PORT)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            printer.nombre,
            printer.print_max,
            printer.tipo,
            printer.genera_packs,
            printer.genera_pallets,
            printer.linea_produccion,
            printer.id_pattern,
            printer.plugin,
            printer.klass,
            printer.activo,
            printer.id_category,
            printer.state,
            printer.host,
            printer.port,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cursor.close()


class MySQLUsuarioRepository(UsuarioRepository):

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def get_existing_user_keys(self) -> set:
        """Carga todas las tuplas (USERNAME, ID_ESLABON) existentes en un set."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT USERNAME, ID_ESLABON FROM usuarios")
        keys = {(row[0], row[1]) for row in cursor.fetchall()}
        cursor.close()
        return keys

    def insert(self, usuario: Usuario) -> None:
        """INSERT con PASSWORD hasheada via MD5() en SQL."""
        sql = """
            INSERT INTO usuarios
                (APEYNOM, USERNAME, PASSWORD, ID_PERFIL, CARGO, MAIL,
                 FACTURA, FECHA_VTO, ID_ESLABON, ACTIVO, FECHA_ALTA)
            VALUES
                (%s, %s, MD5(%s), %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            usuario.APEYNOM,
            usuario.USERNAME,
            usuario.PASSWORD_RAW,
            usuario.ID_PERFIL,
            usuario.CARGO,
            usuario.MAIL,
            usuario.FACTURA,
            usuario.FECHA_VTO,
            usuario.ID_ESLABON,
            usuario.ACTIVO,
            usuario.FECHA_ALTA,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cursor.close()

    def insert_prehashed(self, usuario: Usuario) -> None:
        """INSERT con PASSWORD ya hasheada externamente."""
        sql = """
            INSERT INTO usuarios
                (APEYNOM, USERNAME, PASSWORD, ID_PERFIL, CARGO, MAIL,
                 FACTURA, FECHA_VTO, ID_ESLABON, ACTIVO, FECHA_ALTA)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            usuario.APEYNOM,
            usuario.USERNAME,
            usuario.PASSWORD_RAW,
            usuario.ID_PERFIL,
            usuario.CARGO,
            usuario.MAIL,
            usuario.FACTURA,
            usuario.FECHA_VTO,
            usuario.ID_ESLABON,
            usuario.ACTIVO,
            usuario.FECHA_ALTA,
        )
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cursor.close()


class MySQLPerfilPermisoRepository:

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    def get_all_permisos(self) -> dict:
        """Carga todos los permisos en dict {(ACCION, MODULO, SCRIPT): List[ID_PERMISO]}
        para resolución en memoria sin N+1 queries.
        Una misma combinación (ACCION, MODULO, SCRIPT) puede tener múltiples ID_PERMISO."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT ID_PERMISO, ACCION, MODULO, SCRIPT FROM permiso")
        result: dict = {}
        for row in cursor.fetchall():
            key = (row[1], row[2], row[3])
            result.setdefault(key, []).append(row[0])
        cursor.close()
        return result

    def get_existing_keys(self) -> set:
        """Carga todas las (ID_PERMISO, ID_PERFIL) existentes en un set."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT ID_PERMISO, ID_PERFIL FROM perfil_permiso")
        keys = {(row[0], row[1]) for row in cursor.fetchall()}
        cursor.close()
        return keys

    def bulk_insert_ignore(self, rows: List[tuple]) -> int:
        """INSERT IGNORE INTO perfil_permiso(ID_PERMISO, ID_PERFIL, HABILITADO).
        rows: list of (id_permiso, id_perfil, habilitado).
        Retorna rowcount total."""
        if not rows:
            return 0
        sql = """
            INSERT IGNORE INTO perfil_permiso (ID_PERMISO, ID_PERFIL, HABILITADO)
            VALUES (%s, %s, %s)
        """
        cursor = self._conn.cursor()
        cursor.executemany(sql, rows)
        inserted = cursor.rowcount
        cursor.close()
        return inserted


class MySQLStockRepository:
    """
    Repositorio optimizado para el alta masiva de stock.

    Todas las operaciones usan consultas batch (IN / executemany) para manejar
    volúmenes de hasta 100 000 filas de manera eficiente.
    """

    def __init__(self, connection: MySQLConnection):
        self._conn = connection

    # ── lookups batch ─────────────────────────────────────────────────────────

    def get_medicamento_ids_by_gtins(self, gtins: List[str]) -> dict:
        """SELECT id_medicamento FROM medicamento WHERE bc_ean_1 IN (…) → {gtin: id}."""
        if not gtins:
            return {}
        placeholders = ",".join(["%s"] * len(gtins))
        cursor = self._conn.cursor()
        cursor.execute(
            f"SELECT BC_EAN_1, ID_MEDICAMENTO FROM medicamento WHERE BC_EAN_1 IN ({placeholders})",
            gtins,
        )
        result = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.close()
        return result

    def get_first_usuario_id(self) -> int:
        """Devuelve el ID_USUARIO del primer usuario activo disponible en la tabla."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ID_USUARIO FROM usuarios WHERE ACTIVO = 1 ORDER BY ID_USUARIO LIMIT 1"
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise ValueError(
                "No se encontró ningún usuario activo en la tabla 'usuarios'. "
                "El alta de stock requiere al menos un usuario para registrar el log_estado."
            )
        return row[0]

    def get_eslabon_ids_by_urls(self, urls: List[str]) -> dict:
        """SELECT id_eslabon FROM eslabon WHERE url IN (…) → {url: id}."""
        if not urls:
            return {}
        stripped = [u.strip() for u in urls]
        placeholders = ",".join(["%s"] * len(stripped))
        cursor = self._conn.cursor()
        cursor.execute(
            f"SELECT TRIM(URL), ID_ESLABON FROM eslabon WHERE TRIM(URL) IN ({placeholders})",
            stripped,
        )
        result = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.close()
        return result

    # ── lote ──────────────────────────────────────────────────────────────────

    def bulk_insert_lotes(self, lotes: List[tuple]) -> None:
        """
        INSERT IGNORE INTO lote … en chunks de STOCK_CHUNK_SIZE.

        Cada tupla: (COD_LOTE, FECHA_ALTA, ID_MEDICAMENTO, CANTIDAD, FECHA_VTO, CREADOS, ETIQUETAS)
        """
        if not lotes:
            return
        sql = """
            INSERT IGNORE INTO lote
                (COD_LOTE, FECHA_ALTA, ID_MEDICAMENTO, CANTIDAD, FECHA_VTO, CREADOS, ETIQUETAS)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor = self._conn.cursor()
        for i in range(0, len(lotes), STOCK_CHUNK_SIZE):
            cursor.executemany(sql, lotes[i : i + STOCK_CHUNK_SIZE])
        cursor.close()

    def get_lote_ids_by_cod_lotes(self, cod_lotes: List[str]) -> dict:
        """SELECT id_lote, cod_lote FROM lote WHERE cod_lote IN (…) → {cod_lote: id_lote}."""
        if not cod_lotes:
            return {}
        placeholders = ",".join(["%s"] * len(cod_lotes))
        cursor = self._conn.cursor()
        cursor.execute(
            f"SELECT ID_LOTE, COD_LOTE FROM lote WHERE COD_LOTE IN ({placeholders})",
            cod_lotes,
        )
        result = {row[1]: row[0] for row in cursor.fetchall()}
        cursor.close()
        return result

    # ── etiqueta ──────────────────────────────────────────────────────────────

    def bulk_insert_etiquetas(self, rows: List[tuple]) -> None:
        """
        INSERT IGNORE INTO etiqueta … en chunks de STOCK_CHUNK_SIZE.

        Cada tupla: (GTINSERIE, ESTADO, FECHA_PEDIDO, GTIN, ID_LOTE)
        """
        if not rows:
            return
        sql = """
            INSERT IGNORE INTO etiqueta
                (GTINSERIE, ESTADO, FECHA_PEDIDO, GTIN, ID_LOTE)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor = self._conn.cursor()
        for i in range(0, len(rows), STOCK_CHUNK_SIZE):
            cursor.executemany(sql, rows[i : i + STOCK_CHUNK_SIZE])
        cursor.close()

    # ── item ──────────────────────────────────────────────────────────────────

    def bulk_insert_items(self, rows: List[tuple]) -> None:
        """
        INSERT IGNORE INTO item … en chunks de STOCK_CHUNK_SIZE.

        Cada tupla:
          (ID_ITEM, COD_LOTE, ID_MEDICAMENTO, ID_PACK, ID_PALLET,
           VENDIDO_PAC, ESTADO, ALARMADO, ID_ESLABON_ACT, FECHA_ALTA, EXIGIBLE)
        """
        if not rows:
            return
        sql = """
            INSERT IGNORE INTO item
                (ID_ITEM, COD_LOTE, ID_MEDICAMENTO, ID_PACK, ID_PALLET,
                 VENDIDO_PAC, ESTADO, ALARMADO, ID_ESLABON_ACT, FECHA_ALTA, EXIGIBLE)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor = self._conn.cursor()
        for i in range(0, len(rows), STOCK_CHUNK_SIZE):
            cursor.executemany(sql, rows[i : i + STOCK_CHUNK_SIZE])
        cursor.close()

    # ── log_estado ────────────────────────────────────────────────────────────

    def bulk_insert_log_estados(self, rows: List[tuple]) -> None:
        """
        INSERT IGNORE INTO log_estado … en chunks de STOCK_CHUNK_SIZE.

        Cada tupla:
          (ID_ITEM, TIMESTAMP, TIPO, DESCRIPCION, ID_USUARIO, ESTADO,
           ID_ESLABON_REPORTA, ES_ANMAT, ID_ESLABON_ORIGEN)

        Nota: `TIMESTAMP` es palabra reservada en MySQL y debe escaparse con
        backticks para evitar que el parser lo rechace silenciosamente bajo
        INSERT IGNORE.
        """
        if not rows:
            return
        sql = """
            INSERT IGNORE INTO log_estado
                (ID_ITEM, `TIMESTAMP`, TIPO, DESCRIPCION, ID_USUARIO, ESTADO,
                 ID_ESLABON_REPORTA, ES_ANMAT, ID_ESLABON_ORIGEN)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor = self._conn.cursor()
        total_inserted = 0
        for i in range(0, len(rows), STOCK_CHUNK_SIZE):
            chunk = rows[i : i + STOCK_CHUNK_SIZE]
            cursor.executemany(sql, chunk)
            total_inserted += cursor.rowcount
        cursor.close()
        if total_inserted == 0:
            logger.warning(
                "bulk_insert_log_estados: 0 filas insertadas en log_estado "
                "(posible violación de FK o clave duplicada)."
            )
