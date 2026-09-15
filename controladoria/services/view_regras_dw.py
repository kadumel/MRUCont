"""Cria e atualiza a view consolidada das regras no DW."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from controladoria.services.sql_builder import medidas_ordenadas_codigos

logger = logging.getLogger(__name__)

NOME_VIEW = 'VW_REGRAS_SISTEMA'


class ViewRegrasDWError(Exception):
    pass


def nome_view_dw() -> str:
    schema = settings.DATABASE_SCHEMA_DW
    return f'[{schema}].[{NOME_VIEW}]'


def _dw_disponivel() -> bool:
    return 'dw' in connections.databases


def _sql_view_vazio() -> str:
    dims = [
        ('cdEmpresa', 'NVARCHAR(10)'),
        ('cdEmpreendimento', 'NVARCHAR(11)'),
        ('data', 'DATE'),
    ]
    colunas = [f'CAST(NULL AS {tipo}) AS [{nome}]' for nome, tipo in dims]
    for codigo in medidas_ordenadas_codigos():
        colunas.append(f'CAST(0 AS FLOAT) AS [{codigo}]')
    return f"SELECT\n    {',\n    '.join(colunas)}\nWHERE 1 = 0"


def sql_corpo_view() -> str:
    from controladoria.services.motor_regras import gerar_sql_consolidado

    sql = gerar_sql_consolidado().strip()
    if sql.startswith('--'):
        return _sql_view_vazio()
    return sql


def atualizar_view_regras_dw() -> str:
    """
    Executa CREATE OR ALTER VIEW com o SQL consolidado das regras ativas.
    Retorna o nome qualificado da view (schema.view).
    """
    if not _dw_disponivel():
        raise ViewRegrasDWError('Conexão DW não configurada. Verifique mssql_* no arquivo .env.')

    view = nome_view_dw()
    corpo = sql_corpo_view()
    ddl = f'CREATE OR ALTER VIEW {view} AS\n{corpo}'

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(ddl)
    except OperationalError as exc:
        raise ViewRegrasDWError(f'Erro ao atualizar view {view}: {exc}') from exc

    logger.info('View DW atualizada: %s', view)
    return view
