"""Motor de execução das regras de medida para o BI."""

from __future__ import annotations

from django.db import connections
from django.db.utils import OperationalError

from controladoria.models import AjusteManual, Medida, RegraMedida, TipoAjuste, TipoExcecao
from controladoria.services.sql_builder import (
    build_consulta_bi,
    build_regra_sql,
    medidas_ordenadas_codigos,
)


class MotorRegrasError(Exception):
    pass


def _db_dw_disponivel() -> bool:
    return 'dw' in connections.databases


def obter_regras_ativas() -> list[RegraMedida]:
    return list(
        RegraMedida.objects.filter(ativo=True, medida__ativo=True)
        .select_related('medida')
        .prefetch_related('excecoes')
        .order_by('medida__ordem', 'id')
    )


def obter_medidas_ativas() -> list[Medida]:
    return list(Medida.objects.filter(ativo=True).order_by('ordem', 'codigo'))


def gerar_sql_regra(regra: RegraMedida) -> str:
    return build_regra_sql(regra, medidas_ordenadas=medidas_ordenadas_codigos())


def gerar_sql_consolidado() -> str:
    regras = obter_regras_ativas()
    medidas_com_sql = [(r.medida.codigo, gerar_sql_regra(r)) for r in regras]

    group_by = None
    if regras and regras[0].group_by:
        group_by = []
        for campo in regras[0].group_by:
            if campo.lower().startswith('eomonth('):
                group_by.append('data')
            elif '.' not in campo:
                group_by.append(campo)
            else:
                group_by.append(campo.split('.')[-1])

    return build_consulta_bi(medidas_com_sql, group_by=group_by)


def executar_sql_dw(sql: str, params=None) -> tuple[list[str], list[tuple]]:
    if not _db_dw_disponivel():
        raise MotorRegrasError(
            'Conexão DW não configurada. Verifique mssql_* no arquivo .env.'
        )
    try:
        with connections['dw'].cursor() as cursor:
            cursor.execute(sql, params or [])
            colunas = [col[0] for col in cursor.description] if cursor.description else []
            linhas = cursor.fetchall()
        return colunas, linhas
    except OperationalError as exc:
        raise MotorRegrasError(f'Erro ao executar no DW: {exc}') from exc


def aplicar_ajustes_manuais(colunas: list[str], linhas: list[tuple]) -> tuple[list[str], list[tuple]]:
    """
    Aplica ajustes manuais em memória sobre o resultado agregado.
    Chave de agrupamento: cdEmpresa, cdEmpreendimento, data (competência).
    """
    if not linhas:
        return colunas, linhas

    idx = {c: i for i, c in enumerate(colunas)}
    resultado: dict[tuple, list] = {}

    for linha in linhas:
        chave = (
            linha[idx.get('cdEmpresa', 0)],
            linha[idx.get('cdEmpreendimento', 1)] if 'cdEmpreendimento' in idx else None,
            linha[idx.get('data', 2)] if 'data' in idx else None,
        )
        resultado[chave] = list(linha)

    ajustes = AjusteManual.objects.filter(ativo=True).select_related('medida')
    for ajuste in ajustes:
        codigo = ajuste.medida.codigo
        if codigo not in idx:
            continue
        chave = (ajuste.cd_empresa, ajuste.cd_empreendimento or None, ajuste.data_competencia)
        if chave not in resultado:
            nova = [0.0] * len(colunas)
            if 'cdEmpresa' in idx:
                nova[idx['cdEmpresa']] = ajuste.cd_empresa
            if 'cdEmpreendimento' in idx:
                nova[idx['cdEmpreendimento']] = ajuste.cd_empreendimento
            if 'data' in idx:
                nova[idx['data']] = ajuste.data_competencia
            resultado[chave] = nova

        pos = idx[codigo]
        valor_atual = float(resultado[chave][pos] or 0)
        if ajuste.tipo == TipoAjuste.INCLUSAO:
            resultado[chave][pos] = valor_atual + ajuste.valor
        elif ajuste.tipo == TipoAjuste.EXCLUSAO:
            resultado[chave][pos] = valor_atual - ajuste.valor
        elif ajuste.tipo == TipoAjuste.RECLASSIFICACAO:
            nova_chave = (ajuste.cd_empresa, ajuste.cd_empreendimento or None, ajuste.data_competencia)
            if nova_chave not in resultado:
                nova = list(resultado[chave])
                if 'data' in idx:
                    nova[idx['data']] = ajuste.data_competencia
                resultado[nova_chave] = nova
            resultado[nova_chave][pos] = float(resultado[nova_chave][pos] or 0) + ajuste.valor
            resultado[chave][pos] = valor_atual - ajuste.valor

    return colunas, [tuple(v) for v in resultado.values()]


def executar_medidas(ano_minimo: int | None = None) -> dict:
    """
    Executa todas as regras ativas e retorna SQL, colunas e linhas.
    """
    sql = gerar_sql_consolidado()
    if ano_minimo:
        sql = sql.replace('YEAR(f.Data) >= 2024', f'YEAR(f.Data) >= {ano_minimo}')

    colunas, linhas = executar_sql_dw(sql)
    colunas, linhas = aplicar_ajustes_manuais(colunas, linhas)
    return {
        'sql': sql,
        'colunas': colunas,
        'linhas': linhas,
        'total_linhas': len(linhas),
    }


def preview_regra(regra_id: int, limite: int = 100) -> dict:
    regra = RegraMedida.objects.select_related('medida').prefetch_related('excecoes').get(pk=regra_id)
    sql = gerar_sql_regra(regra)
    sql_limitado = f'SELECT TOP {limite} * FROM (\n{sql}\n) AS preview'
    colunas, linhas = executar_sql_dw(sql_limitado)
    return {'regra': regra, 'sql': sql, 'colunas': colunas, 'linhas': linhas}


def resumo_configuracao() -> dict:
    from controladoria.services.view_regras_dw import NOME_VIEW, nome_view_dw

    return {
        'medidas_ativas': Medida.objects.filter(ativo=True).count(),
        'regras_ativas': RegraMedida.objects.filter(ativo=True, medida__ativo=True).count(),
        'excecoes_ativas': sum(
            r.excecoes.filter(ativo=True).count() for r in RegraMedida.objects.filter(ativo=True)
        ),
        'ajustes_ativos': AjusteManual.objects.filter(ativo=True).count(),
        'dw_configurado': _db_dw_disponivel(),
        'view_regras_dw': nome_view_dw() if _db_dw_disponivel() else None,
        'view_regras_nome': NOME_VIEW,
    }
