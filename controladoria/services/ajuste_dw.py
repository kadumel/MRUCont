"""Sincronização de ajustes com [dbo].[FatoAjusteLancamento] no DW."""

from __future__ import annotations

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from django.utils import timezone

from controladoria.models import AjusteManual


class AjusteDWError(Exception):
    pass


def tabela_ajuste_dw() -> str:
    schema = settings.DATABASE_SCHEMA_DW
    return f'[{schema}].[FatoAjusteLancamento]'


def _dw_disponivel() -> bool:
    return 'dw' in connections.databases


def _null_if_empty(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def _params_ajuste(ajuste: AjusteManual) -> list:
    medida = ajuste.medida
    return [
        ajuste.pk,
        medida.codigo,
        1 if ajuste.ativo else 0,
        _null_if_empty(ajuste.chave_orc),
        _null_if_empty(ajuste.cd_empresa),
        _null_if_empty(ajuste.cd_empreendimento),
        _null_if_empty(ajuste.cd_nucleo),
        _null_if_empty(ajuste.cd_centro),
        ajuste.data_original,
        ajuste.valor_original,
        ajuste.data_competencia,
        ajuste.data_lancamento,
        ajuste.valor,
        _null_if_empty(ajuste.observacao),
    ]


def inserir_ajuste_dw(ajuste: AjusteManual) -> None:
    if not _dw_disponivel():
        raise AjusteDWError('Conexão DW não configurada.')

    if not ajuste.pk:
        raise AjusteDWError('Ajuste sem identificador no app.')

    ajuste = AjusteManual.objects.select_related('medida').get(pk=ajuste.pk)
    tabela = tabela_ajuste_dw()
    sql = f"""
        INSERT INTO {tabela} (
            id_ajuste_app, codigo_medida, ativo,
            chave_orc, cd_empresa, cd_empreendimento, cd_nucleo, cd_centro,
            data_original, valor_original, data_competencia, data_lancamento,
            valor, observacao
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
        )
    """

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql, _params_ajuste(ajuste))
    except OperationalError as exc_err:
        raise AjusteDWError(f'Erro ao gravar ajuste no DW: {exc_err}') from exc_err


def atualizar_ajuste_dw(ajuste: AjusteManual) -> None:
    if not _dw_disponivel():
        raise AjusteDWError('Conexão DW não configurada.')

    if not ajuste.pk:
        raise AjusteDWError('Ajuste sem identificador no app.')

    ajuste = AjusteManual.objects.select_related('medida').get(pk=ajuste.pk)
    tabela = tabela_ajuste_dw()
    sql = f"""
        UPDATE {tabela}
        SET codigo_medida = %s,
            ativo = %s,
            chave_orc = %s,
            cd_empresa = %s,
            cd_empreendimento = %s,
            cd_nucleo = %s,
            cd_centro = %s,
            data_original = %s,
            valor_original = %s,
            data_competencia = %s,
            data_lancamento = %s,
            valor = %s,
            observacao = %s,
            atualizado_em = %s
        WHERE id_ajuste_app = %s
    """
    params = _params_ajuste(ajuste)[1:] + [timezone.now(), ajuste.pk]

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.rowcount == 0:
                inserir_ajuste_dw(ajuste)
    except OperationalError as exc_err:
        raise AjusteDWError(f'Erro ao atualizar ajuste no DW: {exc_err}') from exc_err


def _delete_ajuste_dw(cursor, tabela: str, where_sql: str, params: list) -> int:
    cursor.execute(f'DELETE FROM {tabela} WHERE {where_sql}', params)
    return cursor.rowcount


def remover_ajuste_dw(ajuste: AjusteManual | int) -> int:
    """Remove ajuste no DW por id_ajuste_app ou, em fallback, pelos campos do lançamento."""
    if not _dw_disponivel():
        raise AjusteDWError('Conexão DW não configurada.')

    if isinstance(ajuste, int):
        ajuste = AjusteManual.objects.select_related('medida').filter(pk=ajuste).first()
        if ajuste is None:
            return 0

    tabela = tabela_ajuste_dw()

    try:
        with connections['dw'].cursor() as cursor:
            removidas = _delete_ajuste_dw(cursor, tabela, 'id_ajuste_app = %s', [ajuste.pk])
            if removidas:
                return removidas

            conditions = ['codigo_medida = %s']
            params: list = [ajuste.medida.codigo]

            for coluna, valor in (
                ('chave_orc', ajuste.chave_orc),
                ('cd_empresa', ajuste.cd_empresa),
                ('cd_empreendimento', ajuste.cd_empreendimento),
                ('cd_nucleo', ajuste.cd_nucleo),
                ('cd_centro', ajuste.cd_centro),
            ):
                valor_norm = _null_if_empty(valor)
                if valor_norm is not None:
                    conditions.append(f'{coluna} = %s')
                    params.append(valor_norm)

            if ajuste.data_original is not None:
                conditions.append('data_original = %s')
                params.append(ajuste.data_original)
            if ajuste.valor_original is not None:
                conditions.append('valor_original = %s')
                params.append(ajuste.valor_original)

            conditions.append('data_competencia = %s')
            params.append(ajuste.data_competencia)
            conditions.append('valor = %s')
            params.append(ajuste.valor)

            if len(conditions) > 1:
                return _delete_ajuste_dw(cursor, tabela, ' AND '.join(conditions), params)

            return 0
    except OperationalError as exc_err:
        raise AjusteDWError(f'Erro ao remover ajuste no DW: {exc_err}') from exc_err


def sincronizar_todos_ajustes_dw() -> tuple[int, int]:
    """Reenvia todos os ajustes ativos do app para o DW (limpa e reinsere)."""
    if not _dw_disponivel():
        raise AjusteDWError('Conexão DW não configurada.')

    tabela = tabela_ajuste_dw()
    with connections['dw'].cursor() as cursor:
        cursor.execute(f'DELETE FROM {tabela}')

    inseridas = 0
    erros = 0
    qs = AjusteManual.objects.filter(ativo=True).select_related('medida')

    for ajuste in qs:
        try:
            inserir_ajuste_dw(ajuste)
            inseridas += 1
        except AjusteDWError:
            erros += 1

    return inseridas, erros


def criar_tabela_ajuste_dw() -> None:
    """Cria [FatoAjusteLancamento] no DW se ainda não existir."""
    if not _dw_disponivel():
        raise AjusteDWError('Conexão DW não configurada.')

    tabela = tabela_ajuste_dw()
    sql = f"""
    IF OBJECT_ID(N'{tabela}', N'U') IS NULL
    BEGIN
        CREATE TABLE {tabela} (
            id_ajuste INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            id_ajuste_app INT NOT NULL,
            codigo_medida VARCHAR(80) NOT NULL,
            ativo BIT NOT NULL CONSTRAINT DF_FatoAjusteLancamento_ativo DEFAULT (1),
            chave_orc NVARCHAR(MAX) NULL,
            cd_empresa VARCHAR(10) NOT NULL,
            cd_empreendimento VARCHAR(11) NULL,
            cd_nucleo VARCHAR(3) NULL,
            cd_centro VARCHAR(15) NULL,
            data_original DATE NULL,
            valor_original FLOAT NULL,
            data_competencia DATE NOT NULL,
            data_lancamento DATE NULL,
            valor FLOAT NOT NULL,
            observacao NVARCHAR(MAX) NULL,
            criado_em DATETIME2 NOT NULL CONSTRAINT DF_FatoAjusteLancamento_criado DEFAULT (SYSUTCDATETIME()),
            atualizado_em DATETIME2 NOT NULL CONSTRAINT DF_FatoAjusteLancamento_atualizado DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_FatoAjusteLancamento_app ON {tabela} (id_ajuste_app);
    END
    """

    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql)
    except OperationalError as exc_err:
        raise AjusteDWError(f'Erro ao criar tabela de ajustes no DW: {exc_err}') from exc_err
