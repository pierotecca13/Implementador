"""
Application service — orchestrates the full import flow inside a single MySQL transaction.

Execution order (mandatory):
  1. INSERT IGNORE → eslabon         (Formulario de Registro)
  2. Resolve ID_LAB dinámico         (SELECT ID_ESLABON WHERE ID_EMPRESA=1)
  3. INSERT IGNORE → medicamento     (Formulario de Productos)
  4. INSERT IGNORE → eslabon         (Formulario Proveedores Clientes)
  5. INSERT IGNORE → eslabon_eslabon (cross-product PR + CL relations)
  6. UPDATE        → configuracion   (Parámetros)
  7. INSERT IGNORE → perfil          (hardcoded profiles)
  8. INSERT IGNORE → usuarios        (Formulario de Usuarios)

Any failure → ROLLBACK.  All OK → COMMIT.
"""
from datetime import date, datetime
from typing import List
import calendar

from domain.models import Eslabon, Medicamento, EslabonEslabon, Parametro, Perfil, Printer, Usuario, StockRow
from infrastructure.repositories import (
    MySQLEslabonRepository,
    MySQLMedicamentoRepository,
    MySQLEslabonEslabonRepository,
    MySQLConfiguracionRepository,
    MySQLPerfilRepository,
    MySQLPrinterRepository,
    MySQLUsuarioRepository,
    MySQLStockRepository,
)
from config.settings import PERFILES_HARDCODE, SPECIAL_QUOTED_PARAMS
from utils.logger import get_logger

logger = get_logger()


def _subtract_2_months(d: date) -> date:
    """Resta exactamente 2 meses a una fecha, ajustando el día si el mes destino es más corto."""
    m = d.month - 2
    y = d.year
    if m <= 0:
        m += 12
        y -= 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


class ImportResult:
    """Holds per-section counters for the final summary report."""

    def __init__(self, section: str):
        self.section = section
        self.total = 0
        self.ok = 0
        self.errors = 0
        self.skipped = 0

    def record_ok(self):
        self.total += 1
        self.ok += 1

    def record_error(self):
        self.total += 1
        self.errors += 1

    def record_skipped(self):
        self.total += 1
        self.skipped += 1

    def __str__(self) -> str:
        base = (
            f" [{self.section:<35}] "
            f"{self.total:>3} filas | {self.ok:>3} OK | {self.errors:>3} errores"
        )
        if self.skipped:
            base += f" | {self.skipped:>3} omitidos (no existen en BD)"
        return base


class ImportService:

    def __init__(self, connection):
        self._conn = connection
        self._eslabon_repo         = MySQLEslabonRepository(connection)
        self._medicamento_repo     = MySQLMedicamentoRepository(connection)
        self._eslabon_eslabon_repo = MySQLEslabonEslabonRepository(connection)
        self._configuracion_repo   = MySQLConfiguracionRepository(connection)
        self._perfil_repo          = MySQLPerfilRepository(connection)
        self._printer_repo         = MySQLPrinterRepository(connection)
        self._usuario_repo         = MySQLUsuarioRepository(connection)
        self._stock_repo           = MySQLStockRepository(connection)

    # ── public API ────────────────────────────────────────────────────────────

    def run(
        self,
        registro: List[Eslabon],
        productos: List[Medicamento],
        proveedores: List[Eslabon],
        parametros: List[Parametro],
        impresoras: List[Printer],
        usuarios: List[Usuario],
        stock: List[StockRow] = None,
    ) -> bool:
        if stock is None:
            stock = []
        results: List[ImportResult] = []

        try:
            r1 = self._import_registro(registro)
            results.append(r1)

            id_lab = self._eslabon_repo.get_lab_id()
            logger.info(f"  ID_LAB resuelto dinámicamente: {id_lab}")

            r2 = self._import_productos(productos, id_lab)
            results.append(r2)

            r3 = self._import_proveedores(proveedores)
            results.append(r3)

            r4 = self._import_relaciones()
            results.append(r4)

            r5 = self._import_parametros(parametros)
            results.append(r5)

            r6 = self._import_impresoras(impresoras)
            results.append(r6)

            r7 = self._import_perfiles()
            results.append(r7)

            r8 = self._import_usuarios(usuarios)
            results.append(r8)

            if stock:
                r9 = self._import_stock(stock)
                results.append(r9)

            self._conn.commit()
            self._print_summary(results, success=True)
            return True

        except Exception as exc:
            self._conn.rollback()
            logger.error(f"Error durante la importación: {exc}", exc_info=True)
            self._print_summary(results, success=False)
            return False

    # ── private steps ─────────────────────────────────────────────────────────

    def _import_registro(self, eslabones: List[Eslabon]) -> ImportResult:
        result = ImportResult("Formulario de Registro")
        for eslabon in eslabones:
            try:
                self._eslabon_repo.insert_ignore(eslabon)
                result.record_ok()
                logger.debug(f"  eslabon INSERT IGNORE OK — RSOC={eslabon.RSOC}")
            except Exception as exc:
                result.record_error()
                logger.error(f"  eslabon INSERT error — RSOC={eslabon.RSOC}: {exc}")
                raise

        # Insertar un usuario "interfaz" por cada URL única del sheet de Registro
        unique_urls = list({e.URL for e in eslabones if e.URL})
        today = date.today()
        for url in unique_urls:
            id_eslabon = self._eslabon_repo.get_id_by_url(url)
            if id_eslabon is None:
                logger.warning(
                    f"  No se encontró eslabon para URL '{url}' — usuario interfaz omitido."
                )
                continue
            usuario = Usuario(
                APEYNOM="Interfaz",
                USERNAME="interfaz",
                PASSWORD_RAW="5af0563e8527d1c6b50424729e91c48a",
                ID_PERFIL=1,
                CARGO="SOPORTE-BDEV",
                MAIL=None,
                FACTURA=None,
                FECHA_VTO=None,
                ID_ESLABON=id_eslabon,
                ACTIVO=1,
                FECHA_ALTA=today,
            )
            try:
                self._usuario_repo.insert_ignore_prehashed(usuario)
                result.record_ok()
                logger.debug(
                    f"  usuario interfaz INSERT IGNORE OK — URL={url}, ID_ESLABON={id_eslabon}"
                )
            except Exception as exc:
                result.record_error()
                logger.error(f"  usuario interfaz INSERT error — URL={url}: {exc}")
                raise

        return result

    def _import_productos(self, medicamentos: List[Medicamento], id_lab: int) -> ImportResult:
        result = ImportResult("Formulario de Productos")
        for med in medicamentos:
            med.ID_LAB = id_lab
            try:
                self._medicamento_repo.insert_ignore(med)
                result.record_ok()
                logger.debug(f"  medicamento INSERT IGNORE OK — NOMBRE={med.NOMBRE}")
            except Exception as exc:
                result.record_error()
                logger.error(f"  medicamento INSERT error — NOMBRE={med.NOMBRE}: {exc}")
                raise
        return result

    def _import_proveedores(self, eslabones: List[Eslabon]) -> ImportResult:
        result = ImportResult("Formulario Proveedores Clientes")
        for eslabon in eslabones:
            try:
                self._eslabon_repo.insert_ignore(eslabon)
                result.record_ok()
                logger.debug(f"  eslabon INSERT IGNORE OK — RSOC={eslabon.RSOC}")
            except Exception as exc:
                result.record_error()
                logger.error(f"  eslabon INSERT error — RSOC={eslabon.RSOC}: {exc}")
                raise
        return result

    def _import_relaciones(self) -> ImportResult:
        result = ImportResult("eslabon_eslabon - relaciones")
        ids_with_url    = self._eslabon_repo.get_ids_with_url()
        ids_without_url = self._eslabon_repo.get_ids_without_url()

        logger.info(
            f"  Relaciones: {len(ids_with_url)} eslabones con URL x "
            f"{len(ids_without_url)} eslabones sin URL = "
            f"{len(ids_with_url) * len(ids_without_url) * 2} filas esperadas"
        )

        today = date.today()
        for id_with in ids_with_url:
            for id_without in ids_without_url:
                for tipo in ("PR", "CL"):
                    rel = EslabonEslabon(
                        ID_ESLABON=id_with, ID_RELACION=id_without,
                        TIPO=tipo, ACTIVO=1, FECHA_ALTA=today,
                    )
                    try:
                        self._eslabon_eslabon_repo.insert_ignore(rel)
                        result.record_ok()
                        logger.debug(
                            f"  eslabon_eslabon INSERT IGNORE OK — "
                            f"ID_ESLABON={id_with}, ID_RELACION={id_without}, TIPO={tipo}"
                        )
                    except Exception as exc:
                        result.record_error()
                        logger.error(
                            f"  eslabon_eslabon INSERT error — "
                            f"ID_ESLABON={id_with}, ID_RELACION={id_without}, TIPO={tipo}: {exc}"
                        )
                        raise
        return result

    def _import_parametros(self, parametros: List[Parametro]) -> ImportResult:
        result = ImportResult("Parametros")
        for param in parametros:
            try:
                affected = self._configuracion_repo.update(param)
                if affected == -1:
                    result.record_skipped()
                else:
                    result.record_ok()
                    logger.debug(
                        f"  configuracion UPDATE OK — NOMBRE={param.NOMBRE}"
                        + (" (sin cambio, valor identico)" if affected == 0 else "")
                    )
            except Exception as exc:
                result.record_error()
                logger.error(f"  configuracion UPDATE error — NOMBRE={param.NOMBRE}: {exc}")
                raise
        return result

    def _import_impresoras(self, printers: List[Printer]) -> ImportResult:
        """
        INSERT IGNORE each printer into the `printer` table, then UPDATE
        the configuracion rows dictated by each printer type.
        """
        result = ImportResult("Formulario de Impresoras")
        for printer in printers:
            try:
                self._printer_repo.insert_ignore(printer)
                result.record_ok()
                logger.debug(
                    f"  printer INSERT IGNORE OK — nombre={printer.nombre}, tipo={printer.tipo}"
                )
            except Exception as exc:
                result.record_error()
                logger.error(f"  printer INSERT error — nombre={printer.nombre}: {exc}")
                raise

            for nombre_cfg, valor_cfg in printer.configuracion_updates:
                if nombre_cfg in SPECIAL_QUOTED_PARAMS:
                    valor_cfg = f"'{valor_cfg}'"
                param = Parametro(NOMBRE=nombre_cfg, VALOR=valor_cfg)
                try:
                    affected = self._configuracion_repo.update(param)
                    if affected == -1:
                        logger.info(
                            f"  configuracion '{nombre_cfg}' no existe — omitido "
                            f"(impresora '{printer.nombre}')."
                        )
                    else:
                        logger.debug(
                            f"  configuracion UPDATE OK — NOMBRE={nombre_cfg}, VALOR={valor_cfg}"
                        )
                except Exception as exc:
                    result.record_error()
                    logger.error(
                        f"  configuracion UPDATE error — NOMBRE={nombre_cfg}: {exc}"
                    )
                    raise
        return result

    def _import_perfiles(self) -> ImportResult:
        """INSERT IGNORE the 4 hardcoded profiles that must always exist."""
        result = ImportResult("Perfiles")
        for p in PERFILES_HARDCODE:
            perfil = Perfil(ID_PERFIL=p["ID_PERFIL"], NOMBRE=p["NOMBRE"])
            try:
                self._perfil_repo.insert_ignore(perfil)
                result.record_ok()
                logger.debug(
                    f"  perfil INSERT IGNORE OK — ID={perfil.ID_PERFIL}, NOMBRE={perfil.NOMBRE}"
                )
            except Exception as exc:
                result.record_error()
                logger.error(f"  perfil INSERT error — NOMBRE={perfil.NOMBRE}: {exc}")
                raise
        return result

    def _import_usuarios(self, usuarios: List[Usuario]) -> ImportResult:
        """
        Resolve ID_PERFIL (from perfil.NOMBRE) and ID_ESLABON (from eslabon.URL),
        then INSERT IGNORE each usuario. PASSWORD is hashed via MD5() in SQL.
        """
        result = ImportResult("Formulario de Usuarios")

        for usuario in usuarios:
            # Resolve perfil name → ID_PERFIL
            perfil_nombre = str(usuario.ID_PERFIL)
            id_perfil = self._perfil_repo.get_id_by_nombre(perfil_nombre)
            if id_perfil is None:
                msg = (
                    f"Perfil '{perfil_nombre}' no encontrado en tabla perfil "
                    f"para usuario '{usuario.USERNAME}'."
                )
                logger.error(f"  {msg}")
                raise ValueError(msg)
            usuario.ID_PERFIL = id_perfil

            # Resolve URL → ID_ESLABON
            url_acceso = str(usuario.ID_ESLABON)
            id_eslabon = self._eslabon_repo.get_id_by_url(url_acceso)
            if id_eslabon is None:
                msg = (
                    f"URL '{url_acceso}' no encontrada en tabla eslabon "
                    f"para usuario '{usuario.USERNAME}'."
                )
                logger.error(f"  {msg}")
                raise ValueError(msg)
            usuario.ID_ESLABON = id_eslabon

            try:
                self._usuario_repo.insert_ignore(usuario)
                result.record_ok()
                logger.debug(
                    f"  usuario INSERT IGNORE OK — USERNAME={usuario.USERNAME}, "
                    f"ID_PERFIL={id_perfil}, ID_ESLABON={id_eslabon}"
                )
            except Exception as exc:
                result.record_error()
                logger.error(f"  usuario INSERT error — USERNAME={usuario.USERNAME}: {exc}")
                raise

        return result

    def _import_stock(self, stock_rows: List[StockRow]) -> ImportResult:
        """
        Alta masiva de stock desde 'Formulario de Stock'.

        Estrategia de performance para ~100 000 filas:
          1. Un único SELECT IN para resolver id_medicamento por GTIN único.
          2. Un único SELECT IN para resolver id_eslabon por URL única.
          3. Deduplica lotes (por cod_lote) y hace un bulk INSERT IGNORE.
          4. Un único SELECT IN para recuperar los id_lote recién generados.
          5. Construye todas las tuplas en memoria y hace bulk INSERT IGNORE
             de etiqueta, item y log_estado en chunks de STOCK_CHUNK_SIZE.
        """
        result = ImportResult("Formulario de Stock")

        now        = datetime.now()
        today      = now.date()
        ts_now     = now.strftime("%Y-%m-%d %H:%M:%S")

        fecha_2m   = _subtract_2_months(today)
        ts_2m      = f"{fecha_2m} {now.strftime('%H:%M:%S')}"

        # 0. Resolver ID_USUARIO para el log_estado
        id_usuario = self._stock_repo.get_first_usuario_id()
        logger.info(f"  Stock: usando ID_USUARIO={id_usuario} para log_estado.")

        # 1. Resolver id_medicamento por GTINs únicos
        unique_gtins = list({r.gtin for r in stock_rows})
        gtin_to_med  = self._stock_repo.get_medicamento_ids_by_gtins(unique_gtins)
        missing = [g for g in unique_gtins if g not in gtin_to_med]
        if missing:
            raise ValueError(
                f"[Formulario de Stock] GTINs no encontrados en medicamento: {missing}"
            )

        # 2. Resolver id_eslabon por URLs únicas
        unique_urls   = list({r.url_acceso for r in stock_rows})
        url_to_eslabon = self._stock_repo.get_eslabon_ids_by_urls(unique_urls)
        missing = [u for u in unique_urls if u not in url_to_eslabon]
        if missing:
            raise ValueError(
                f"[Formulario de Stock] URLs no encontradas en eslabon: {missing}"
            )

        # 3. Deduplicar lotes — una sola fila por cod_lote
        seen_lotes: dict = {}
        for r in stock_rows:
            if r.cod_lote not in seen_lotes:
                seen_lotes[r.cod_lote] = (
                    r.cod_lote,          # COD_LOTE
                    today,               # FECHA_ALTA
                    gtin_to_med[r.gtin], # ID_MEDICAMENTO
                    0,                   # CANTIDAD
                    r.fecha_vto,         # FECHA_VTO
                    0,                   # CREADOS
                    0,                   # ETIQUETAS
                )

        lotes_tuples = list(seen_lotes.values())
        logger.info(
            f"  Stock: {len(lotes_tuples)} lotes únicos | {len(stock_rows)} series"
        )

        # 4. Bulk INSERT lotes y recuperar sus IDs
        self._stock_repo.bulk_insert_lotes(lotes_tuples)
        cod_lote_to_id = self._stock_repo.get_lote_ids_by_cod_lotes(list(seen_lotes))
        missing = [c for c in seen_lotes if c not in cod_lote_to_id]
        if missing:
            raise ValueError(
                f"[Formulario de Stock] No se pudieron recuperar IDs de lote para: {missing}"
            )

        # 5. Construir tuplas para etiqueta / item / log_estado
        etiquetas:   List[tuple] = []
        items:       List[tuple] = []
        log_estados: List[tuple] = []

        for r in stock_rows:
            gtin_14   = r.gtin if len(r.gtin) == 14 else "0" + r.gtin
            gtinserie = "01" + gtin_14 + "21" + r.serie
            id_lote   = cod_lote_to_id[r.cod_lote]
            id_med    = gtin_to_med[r.gtin]
            id_eslabon = url_to_eslabon[r.url_acceso]

            etiquetas.append((
                gtinserie,   # GTINSERIE
                "pegada",    # ESTADO
                ts_now,      # FECHA_PEDIDO
                r.gtin,      # GTIN
                id_lote,     # ID_LOTE
            ))

            items.append((
                gtinserie,   # ID_ITEM
                r.cod_lote,  # COD_LOTE
                id_med,      # ID_MEDICAMENTO
                r.id_pack,   # ID_PACK
                r.id_pallet, # ID_PALLET
                0,           # VENDIDO_PAC
                "ST",        # ESTADO
                0,           # ALARMADO
                id_eslabon,  # ID_ESLABON_ACT
                fecha_2m,    # FECHA_ALTA  (hoy − 2 meses)
                1,           # EXIGIBLE
            ))

            log_estados.append((
                gtinserie,                       # ID_ITEM
                ts_2m,                           # TIMESTAMP  (hoy − 2 meses)
                "Stock",                         # TIPO
                "El item es ingresado a stock",  # DESCRIPCION
                id_usuario,                      # ID_USUARIO
                "ST",                            # ESTADO
                id_eslabon,                      # ID_ESLABON_REPORTA
                0,                               # ES_ANMAT
                id_eslabon,                      # ID_ESLABON_ORIGEN
            ))

        self._stock_repo.bulk_insert_etiquetas(etiquetas)
        self._stock_repo.bulk_insert_items(items)
        self._stock_repo.bulk_insert_log_estados(log_estados)

        result.total = len(stock_rows)
        result.ok    = len(stock_rows)
        logger.info(f"  Stock: {len(stock_rows)} series insertadas.")
        return result

    # ── summary printer ───────────────────────────────────────────────────────

    @staticmethod
    def _print_summary(results: List[ImportResult], success: bool) -> None:
        separator = "=" * 60
        thin_sep  = "-" * 60
        print(f"\n{separator}")
        print(" RESUMEN DE IMPORTACION")
        print(separator)
        for r in results:
            print(str(r))
        print(thin_sep)
        if success:
            print(" RESULTADO: SUCCESS — COMMIT realizado")
        else:
            print(" RESULTADO: ERROR — ROLLBACK ejecutado")
        print(f"{separator}\n")
