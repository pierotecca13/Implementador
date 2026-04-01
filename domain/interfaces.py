"""Abstract repository interfaces — defines the contract, not the implementation."""
from abc import ABC, abstractmethod
from typing import List, Optional

from domain.models import Eslabon, Medicamento, EslabonEslabon, Parametro, Perfil, Printer, Usuario


class EslabonRepository(ABC):

    @abstractmethod
    def insert_ignore(self, eslabon: Eslabon) -> bool:
        """INSERT IGNORE a single Eslabon. Returns True if inserted."""

    @abstractmethod
    def get_ids_with_url(self) -> List[int]:
        """Return all ID_ESLABON where URL IS NOT NULL."""

    @abstractmethod
    def get_ids_without_url(self) -> List[int]:
        """Return all ID_ESLABON where URL IS NULL."""

    @abstractmethod
    def get_id_by_url(self, url: str) -> Optional[int]:
        """Return ID_ESLABON matching the given URL, or None if not found."""


class MedicamentoRepository(ABC):

    @abstractmethod
    def insert_ignore(self, medicamento: Medicamento) -> bool:
        """INSERT IGNORE a single Medicamento. Returns True if inserted."""


class EslabonEslabonRepository(ABC):

    @abstractmethod
    def insert_ignore(self, rel: EslabonEslabon) -> bool:
        """INSERT IGNORE a single EslabonEslabon relation. Returns True if inserted."""


class ConfiguracionRepository(ABC):

    @abstractmethod
    def update(self, parametro: Parametro) -> int:
        """UPDATE configuracion SET VALOR WHERE NOMBRE. Returns rows affected."""


class PerfilRepository(ABC):

    @abstractmethod
    def insert_ignore(self, perfil: Perfil) -> bool:
        """INSERT IGNORE a single Perfil. Returns True if inserted."""

    @abstractmethod
    def get_id_by_nombre(self, nombre: str) -> Optional[int]:
        """Return ID_PERFIL matching the given NOMBRE, or None if not found."""


class PrinterRepository(ABC):

    @abstractmethod
    def insert_ignore(self, printer: Printer) -> bool:
        """INSERT IGNORE a single Printer. Returns True if inserted."""


class UsuarioRepository(ABC):

    @abstractmethod
    def insert_ignore(self, usuario: Usuario) -> bool:
        """INSERT IGNORE a single Usuario (PASSWORD hashed via MD5 in SQL)."""
