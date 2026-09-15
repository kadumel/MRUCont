"""Sincronização de empresas com [dbo].[DimEmpresa] no DW."""

from __future__ import annotations

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from controladoria.models import Empresa


class EmpresaDWError(Exception):
    pass


def tabela_dim_empresa_dw() -> str:
    schema = settings.DATABASE_SCHEMA_DW
    return f'[{schema}].[DimEmpresa]'


def _dw_disponivel() -> bool:
    return 'dw' in connections.databases


def _params_empresa(empresa: Empresa) -> list:
    return [
        empresa.empresa.strip().upper(),
        empresa.nome.strip(),
        empresa.segmento,
    ]


def sincronizar_empresa_dw(empresa: Empresa) -> None:
    """
    Insere ou atualiza DimEmpresa pelo cdEmpresa.
    Atualiza Filial_Nome e Segmento quando o código já existir.
    """
    if not _dw_disponivel():
        raise EmpresaDWError('Conexão DW não configurada.')

    if not empresa.empresa:
        raise EmpresaDWError('Empresa sem código para sincronizar com o DW.')

    tabela = tabela_dim_empresa_dw()
    cd_empresa, filial_nome, segmento = _params_empresa(empresa)

    sql = f"""
        MERGE {tabela} AS target
        USING (SELECT %s AS cdEmpresa, %s AS Filial_Nome, %s AS Segmento) AS source
        ON target.cdEmpresa = source.cdEmpresa
        WHEN MATCHED THEN
            UPDATE SET
                Filial_Nome = source.Filial_Nome,
                Segmento = source.Segmento
        WHEN NOT MATCHED THEN
            INSERT (cdEmpresa, Filial_Nome, Segmento)
            VALUES (source.cdEmpresa, source.Filial_Nome, source.Segmento);
    """

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql, [cd_empresa, filial_nome, segmento])
    except OperationalError as exc_err:
        raise EmpresaDWError(f'Erro ao sincronizar empresa no DW: {exc_err}') from exc_err


def remover_empresa_dw(empresa: Empresa | str) -> int:
    """Remove empresa no DW pelo cdEmpresa."""
    if not _dw_disponivel():
        raise EmpresaDWError('Conexão DW não configurada.')

    if isinstance(empresa, Empresa):
        cd_empresa = empresa.empresa.strip().upper()
    else:
        cd_empresa = str(empresa).strip().upper()

    if not cd_empresa:
        return 0

    tabela = tabela_dim_empresa_dw()

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(f'DELETE FROM {tabela} WHERE cdEmpresa = %s', [cd_empresa])
            return cursor.rowcount
    except OperationalError as exc_err:
        raise EmpresaDWError(f'Erro ao remover empresa no DW: {exc_err}') from exc_err


def sincronizar_todas_empresas_dw() -> tuple[int, int]:
    """Sincroniza todas as empresas do app para o DW."""
    if not _dw_disponivel():
        raise EmpresaDWError('Conexão DW não configurada.')

    sincronizadas = 0
    erros = 0

    for empresa in Empresa.objects.all():
        try:
            sincronizar_empresa_dw(empresa)
            sincronizadas += 1
        except EmpresaDWError:
            erros += 1

    return sincronizadas, erros
