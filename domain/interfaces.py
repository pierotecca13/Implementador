"""Abstract repository interfaces — defines the contract, not the implementation."""
from abc import ABC, abstractmethod
from typing import List, Optional, Set, Tuple

from domain.models import Eslabon, Medicamento, EslabonEslabon, Parametro, Perfil, Printer, Usuario


class EslabonRepository(ABC):

    @abstractmethod
    def get_existing_glns(self) -> set:
        """Return all existing GLN values as a set."""

    @abstractmethod
    def insert(self, eslabon: Eslabon) -> None:
        """INSERT a single Eslabon (caller guarantees no duplicate GLN)."""

    @abstractmethod
    def get_ids_with_url(self) -> List[int]:
        """Return all ID_ESLABON where URL IS NOT NULL."""

    @abstractmethod
    def get_ids_without_url(self) -> List[int]:
        """Return all ID_ESLABON where URL IS NULL."""

    @abstractmethod
    def get_id_by_url(self, url: str) -> Optional[int]:
        """Return ID_ESLABON matching the given URL, or None if not found."""

    @abstractmethod
    def get_id_by_gln(self, gln: str) -> Optional[int]:
        """Return ID_ESLABON matching the given GLN, or None if not found."""


class MedicamentoRepository(ABC):

    @abstractmethod
    def insert_ignore(self, medicamento: Medicamento) -> bool:
        """INSERT IGNORE a single Medicamento. Returns True if inserted."""


class EslabonEslabonRepository(ABC):

    @abstractmethod
    def get_existing_relations(self) -> set:
        """Return all existing (ID_ESLABON, ID_RELACION, TIPO) tuples as a set."""

    @abstractmethod
    def insert(self, rel: EslabonEslabon) -> None:
        """INSERT a single EslabonEslabon relation (caller guarantees no duplicate)."""


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
    def get_existing_nombres(self) -> set:
        """Return all existing printer nombres as a set."""

    @abstractmethod
    def insert(self, printer: Printer) -> None:
        """INSERT a single Printer (caller guarantees no duplicate nombre)."""


class UsuarioRepository(ABC):

    @abstractmethod
    def get_existing_user_keys(self) -> set:
        """Return all existing (USERNAME, ID_ESLABON) tuples as a set."""

    @abstractmethod
    def insert(self, usuario: Usuario) -> None:
        """INSERT a single Usuario (PASSWORD hashed via MD5 in SQL)."""

    @abstractmethod
    def insert_prehashed(self, usuario: Usuario) -> None:
        """INSERT a single Usuario with PASSWORD already hashed."""
