"""Domain models — pure dataclasses, no framework dependencies."""
from dataclasses import dataclass, field
from typing import Optional
from datetime import date


@dataclass
class Eslabon:
    RSOC: Optional[str]
    GLN: Optional[str]
    CUIT: Optional[str]
    ID_EMPRESA: int
    ACTIVO: int = 1
    USER_ANMAT: Optional[str] = None
    PASS_ANMAT: Optional[str] = None
    URL: Optional[str] = None
    DIRECCION: Optional[str] = None


@dataclass
class Medicamento:
    NOMBRE: Optional[str]
    BC_EAN_1: Optional[str]
    BC_EAN_2: Optional[str]
    ITEMS_POR_PACK: Optional[int]
    PACKS_POR_PALLET: Optional[int]
    ID_LAB: int = 1
    TRAZABLE: int = 1
    EXIGIBLE: int = 1
    ACTIVO: int = 1
    SERIE: int = 1
    CANTIDAD_CAPAS_PACK: Optional[int] = None
    LEVEL_AGGREGATION: Optional[int] = None


@dataclass
class EslabonEslabon:
    ID_ESLABON: int
    ID_RELACION: int
    TIPO: str          # 'PR' or 'CL'
    ACTIVO: int = 1
    FECHA_ALTA: date = field(default_factory=date.today)


@dataclass
class Parametro:
    NOMBRE: str
    VALOR: str


@dataclass
class Perfil:
    ID_PERFIL: int
    NOMBRE: str


@dataclass
class Printer:
    nombre: str
    print_max: str
    tipo: str
    genera_packs: int
    genera_pallets: int
    linea_produccion: int
    id_pattern: int
    plugin: str
    klass: str              # 'class' column in DB — 'class' is a Python keyword
    host: Optional[str]
    port: int
    activo: int = 1
    id_category: Optional[int] = None
    state: str = "RE"
    configuracion_updates: list = field(default_factory=list)  # [(NOMBRE, VALOR), ...]


@dataclass
class StockRow:
    """Una fila de la pestaña 'Formulario de Stock' (una serie/item)."""
    cod_lote:   str
    gtin:       str
    fecha_vto:  date
    serie:      str
    id_pack:    str   # '0' si el campo estaba vacío
    id_pallet:  str   # '0' si el campo estaba vacío
    url_acceso: str


@dataclass
class Usuario:
    APEYNOM: Optional[str]
    USERNAME: str
    PASSWORD_RAW: str       # plain text — MD5() applied in SQL
    ID_PERFIL: int          # resolved via perfil.NOMBRE lookup
    CARGO: Optional[str]
    MAIL: Optional[str]
    FACTURA: str            # 'BONIFICADO' or 'pendiente'
    FECHA_VTO: Optional[date]   # None if BONIFICADO, today+1year if pendiente
    ID_ESLABON: int         # resolved from eslabon.URL lookup
    ACTIVO: int = 1
    FECHA_ALTA: date = field(default_factory=date.today)
