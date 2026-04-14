#!/usr/bin/env python3
"""
CLI entry point.

Usage:
    python main.py --file Formulario_Masterdata_v3.xlsx
"""
import argparse
import sys
import os

# Allow absolute imports from the project root when running main.py directly
sys.path.insert(0, os.path.dirname(__file__))

from infrastructure.db_connection import get_connection
from infrastructure.excel_reader import read_workbook
from application.import_service import ImportService
from utils.logger import get_logger

logger = get_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa configuración desde un fichero Excel a MySQL."
    )
    parser.add_argument(
        "--file",
        required=True,
        metavar="PATH",
        help="Ruta al fichero Excel (ej: Formulario_Masterdata_v3.xlsx)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.path.isfile(args.file):
        logger.error(f"Fichero no encontrado: {args.file}")
        return 1

    # 1. Read Excel — pure parsing, no DB yet
    try:
        data = read_workbook(args.file)
    except Exception as exc:
        logger.error(f"Error al leer el fichero Excel: {exc}", exc_info=True)
        return 1

    logger.info(
        f"Fichero leído — "
        f"Registro: {len(data['registro'])} filas, "
        f"Productos: {len(data['productos'])} filas, "
        f"Proveedores: {len(data['proveedores'])} filas, "
        f"Usuarios: {len(data['usuarios'])} filas, "
        f"Parámetros: {len(data['parametros'])} filas, "
        f"Impresoras: {len(data['impresoras'])} filas activas, "
        f"Stock: {len(data['stock'])} series, "
        f"Perfil Permiso: {len(data['perfil_permiso'])} filas"
    )

    # 2. Connect to MySQL
    try:
        conn = get_connection()
    except Exception as exc:
        logger.error(f"No se pudo conectar a la base de datos: {exc}", exc_info=True)
        return 1

    # 3. Run import inside a single transaction
    try:
        service = ImportService(conn)
        success = service.run(
            registro=data["registro"],
            productos=data["productos"],
            proveedores=data["proveedores"],
            parametros=data["parametros"],
            impresoras=data["impresoras"],
            usuarios=data["usuarios"],
            stock=data["stock"],
            perfil_permiso=data["perfil_permiso"],
        )
        return 0 if success else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
