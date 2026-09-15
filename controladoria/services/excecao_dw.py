"""Sincronização de exceções com [dbo].[FatoExcecaoLancamento] no DW."""

from __future__ import annotations

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from controladoria.models import ExcecaoLancamento, TipoExcecao


class ExcecaoDWError(Exception):
    pass


def tabela_excecao_dw() -> str:
    schema = settings.DATABASE_SCHEMA_DW
    return f'[{schema}].[FatoExcecaoLancamento]'


def _dw_disponivel() -> bool:
    return 'dw' in connections.databases


def _null_if_empty(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def inserir_excecao_dw(exc: ExcecaoLancamento) -> None:
    if not _dw_disponivel():
        raise ExcecaoDWError('Conexão DW não configurada.')

    regra = exc.regra
    medida = regra.medida
    tabela = tabela_excecao_dw()

    sql = f"""
        INSERT INTO {tabela} (
            id_excecao_app, id_regra, codigo_medida, tipo, ativo,
            chave_orc, cd_empresa, cd_empreendimento, cd_nucleo, cd_centro,
            [data], assunto, classificacao, cliente_fornecedor, valor, motivo
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
    """
    params = [
        exc.pk,
        regra.pk,
        medida.codigo,
        exc.tipo,
        1 if exc.ativo else 0,
        _null_if_empty(exc.chave_orc),
        _null_if_empty(exc.cd_empresa),
        _null_if_empty(exc.cd_empreendimento),
        _null_if_empty(exc.cd_nucleo),
        _null_if_empty(exc.cd_centro),
        exc.data,
        _null_if_empty(exc.assunto),
        _null_if_empty(exc.classificacao),
        _null_if_empty(exc.cliente_fornecedor),
        exc.valor,
        _null_if_empty(exc.motivo),
    ]

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql, params)
    except OperationalError as exc_err:
        raise ExcecaoDWError(f'Erro ao gravar exceção no DW: {exc_err}') from exc_err


def _delete_excecao_dw(cursor, tabela: str, where_sql: str, params: list) -> int:
    cursor.execute(f'DELETE FROM {tabela} WHERE {where_sql}', params)
    return cursor.rowcount


def remover_excecao_dw(exc: ExcecaoLancamento | int) -> int:
    """Remove exceção no DW por id_excecao_app ou, em fallback, pelos campos do lançamento."""
    if not _dw_disponivel():
        raise ExcecaoDWError('Conexão DW não configurada.')

    if isinstance(exc, int):
        exc = ExcecaoLancamento.objects.select_related('regra').filter(pk=exc).first()
        if exc is None:
            return 0

    tabela = tabela_excecao_dw()

    try:
        with connections['dw'].cursor() as cursor:
            removidas = _delete_excecao_dw(
                cursor, tabela, 'id_excecao_app = %s', [exc.pk],
            )
            if removidas:
                return removidas

            if exc.chave_orc:
                removidas = _delete_excecao_dw(
                    cursor,
                    tabela,
                    'id_regra = %s AND chave_orc = %s',
                    [exc.regra_id, exc.chave_orc.strip()],
                )
                if removidas:
                    return removidas

            conditions = ['id_regra = %s']
            params: list = [exc.regra_id]
            for coluna, valor in (
                ('cd_empresa', exc.cd_empresa),
                ('cd_empreendimento', exc.cd_empreendimento),
                ('cd_nucleo', exc.cd_nucleo),
                ('cd_centro', exc.cd_centro),
                ('assunto', exc.assunto),
                ('classificacao', exc.classificacao),
                ('cliente_fornecedor', exc.cliente_fornecedor),
            ):
                valor_norm = _null_if_empty(valor)
                if valor_norm is not None:
                    conditions.append(f'{coluna} = %s')
                    params.append(valor_norm)

            if exc.data is not None:
                conditions.append('[data] = %s')
                params.append(exc.data)
            if exc.valor is not None:
                conditions.append('valor = %s')
                params.append(exc.valor)

            if len(conditions) > 1:
                return _delete_excecao_dw(cursor, tabela, ' AND '.join(conditions), params)

            return 0
    except OperationalError as exc_err:
        raise ExcecaoDWError(f'Erro ao remover exceção no DW: {exc_err}') from exc_err


def sincronizar_todas_excecoes_dw() -> tuple[int, int]:
    """Reenvia todas as exceções ativas do app para o DW (limpa e reinsere)."""
    if not _dw_disponivel():
        raise ExcecaoDWError('Conexão DW não configurada.')

    tabela = tabela_excecao_dw()
    with connections['dw'].cursor() as cursor:
        cursor.execute(f'DELETE FROM {tabela}')

    inseridas = 0
    erros = 0
    qs = ExcecaoLancamento.objects.filter(
        ativo=True,
        tipo=TipoExcecao.EXCLUIR,
    ).select_related('regra', 'regra__medida')

    for exc in qs:
        try:
            inserir_excecao_dw(exc)
            inseridas += 1
        except ExcecaoDWError:
            erros += 1

    return inseridas, erros
