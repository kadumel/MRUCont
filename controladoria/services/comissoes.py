"""Consulta de comissões de parcerias no DW e inclusão na base local."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.conf import settings

from controladoria.models import Comissao
from controladoria.services.motor_regras import MotorRegrasError, executar_sql_dw

PAGE_SIZE = 50

STATUS_ELEGIBILIDADE_TODOS = 'todos'
STATUS_ELEGIBILIDADE_ATINGIU = 'atingiu'
STATUS_ELEGIBILIDADE_NAO_ATINGIU = 'nao_atingiu'
STATUS_ELEGIBILIDADE_CHOICES = {
    STATUS_ELEGIBILIDADE_TODOS,
    STATUS_ELEGIBILIDADE_ATINGIU,
    STATUS_ELEGIBILIDADE_NAO_ATINGIU,
}


class ComissaoError(Exception):
    pass


def _schema() -> str:
    return settings.DATABASE_SCHEMA_DW


def _sql_base(excluir_contratos: bool = True) -> str:
    schema = _schema()
    exclusao = ''
    if excluir_contratos:
        contratos = list(Comissao.objects.values_list('cd_contrato', flat=True))
        if contratos:
            placeholders = ', '.join(['%s'] * len(contratos))
            exclusao = f'AND i.cdContrato NOT IN ({placeholders})'

    return f"""
SELECT
    i.Data,
    i.cdEmpresa,
    i.cdContrato,
    i.Contrato,
    i.Situacao,
    i.cdCliente,
    i.Cliente,
    i.ValorTabelaPrimeira,
    i.ValorTabelaVenda,
    i.ValorVendaAVista,
    i.Desconto,
    d.Liquidado,
    e.Percentual,
    i.ValorVendaAVista * e.Percentual AS Comissao
FROM {schema}.FatoImoveisParcerias i
JOIN {schema}.DimEmpresa e ON e.cdEmpresa = i.cdEmpresa
JOIN (
    SELECT cdContrato, SUM(vlPrincipal + vlReajuste) AS Liquidado
    FROM {schema}.FatoTitulosReceberQ01
    WHERE tpParcela NOT LIKE 'tax%%'
      AND dtPagto IS NOT NULL
      AND dtPagto <= %s
    GROUP BY cdContrato
) d ON d.cdContrato = i.cdContrato
WHERE 1 = 1
{exclusao}
"""


def _parse_data(valor) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def _decimal_valor(valor) -> Decimal | None:
    if valor is None or valor == '':
        return None
    return Decimal(str(valor))


def _elegivel_pagamento(liquidado, comissao) -> bool:
    liq = _decimal_valor(liquidado)
    com = _decimal_valor(comissao)
    if liq is None or com is None:
        return False
    return liq >= com


def _where_status_elegibilidade(status_elegibilidade: str) -> str:
    expr = 'i.ValorVendaAVista * e.Percentual'
    if status_elegibilidade == STATUS_ELEGIBILIDADE_ATINGIU:
        return f'AND d.Liquidado >= {expr}'
    if status_elegibilidade == STATUS_ELEGIBILIDADE_NAO_ATINGIU:
        return f'AND d.Liquidado < {expr}'
    return ''


def _linha_para_dict(colunas: list[str], linha: tuple) -> dict:
    row = dict(zip(colunas, linha))
    data_fmt = _parse_data(row.get('Data'))
    return {
        'data_contrato': data_fmt,
        'data_contrato_fmt': data_fmt,
        'cd_empresa': row.get('cdEmpresa') or '',
        'cd_contrato': row.get('cdContrato') or '',
        'contrato': row.get('Contrato') or '',
        'situacao': row.get('Situacao') or '',
        'cd_cliente': row.get('cdCliente') or '',
        'cliente': row.get('Cliente') or '',
        'valor_tabela_primeira': row.get('ValorTabelaPrimeira'),
        'valor_tabela_venda': row.get('ValorTabelaVenda'),
        'valor_venda_a_vista': row.get('ValorVendaAVista'),
        'desconto': row.get('Desconto'),
        'liquidado': row.get('Liquidado'),
        'percentual': row.get('Percentual'),
        'percentual_pct': (float(row['Percentual']) * 100) if row.get('Percentual') is not None else None,
        'comissao': row.get('Comissao'),
        'elegivel_pagamento': _elegivel_pagamento(row.get('Liquidado'), row.get('Comissao')),
    }


def buscar_comissoes_dw(
    data_corte: date,
    mes_fechamento: int | None = None,
    ano_fechamento: int | None = None,
    pagina: int = 1,
    status_elegibilidade: str = STATUS_ELEGIBILIDADE_TODOS,
) -> dict:
    if not data_corte:
        raise ComissaoError('Informe a data de corte.')

    if status_elegibilidade not in STATUS_ELEGIBILIDADE_CHOICES:
        raise ComissaoError('Status de elegibilidade inválido.')

    contratos_excluidos = list(Comissao.objects.values_list('cd_contrato', flat=True))
    params: list = [data_corte.isoformat()]
    params.extend(contratos_excluidos)

    where_extra = _where_status_elegibilidade(status_elegibilidade)
    if mes_fechamento and ano_fechamento:
        where_extra += ' AND YEAR(i.Data) = %s AND MONTH(i.Data) = %s'
        params.extend([ano_fechamento, mes_fechamento])

    offset = max(pagina - 1, 0) * PAGE_SIZE
    sql_count = f"""
SELECT COUNT(*) AS total
FROM (
    {_sql_base(excluir_contratos=bool(contratos_excluidos)).strip()}
    {where_extra}
) AS sub
"""

    try:
        _, count_rows = executar_sql_dw(sql_count, params)
    except MotorRegrasError as exc:
        raise ComissaoError(str(exc)) from exc

    total = int(count_rows[0][0]) if count_rows else 0
    total_paginas = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    pagina = min(max(pagina, 1), total_paginas)
    offset = (pagina - 1) * PAGE_SIZE

    sql_page = f"""
{_sql_base(excluir_contratos=bool(contratos_excluidos)).strip()}
{where_extra}
ORDER BY i.Data DESC, i.cdContrato
OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY
"""

    try:
        colunas, linhas = executar_sql_dw(sql_page, params)
    except MotorRegrasError as exc:
        raise ComissaoError(str(exc)) from exc

    registros = [_linha_para_dict(colunas, linha) for linha in linhas]

    return {
        'registros': registros,
        'total': total,
        'pagina': pagina,
        'total_paginas': total_paginas,
        'page_size': PAGE_SIZE,
    }


def incluir_comissao(
    dados: dict,
    data_pagamento: date,
    data_corte: date,
    mes_fechamento: int | None,
    ano_fechamento: int | None,
    usuario=None,
) -> Comissao:
    cd_contrato = (dados.get('cd_contrato') or '').strip()
    if not cd_contrato:
        raise ComissaoError('Contrato inválido.')

    if Comissao.objects.filter(cd_contrato=cd_contrato).exists():
        raise ComissaoError(f'O contrato {cd_contrato} já foi incluído para pagamento.')

    if not data_pagamento:
        raise ComissaoError('Informe a data de pagamento.')

    def _decimal(valor):
        if valor is None or valor == '':
            return None
        return Decimal(str(valor))

    liquidado = _decimal(dados.get('liquidado'))
    comissao = _decimal(dados.get('comissao'))
    if not _elegivel_pagamento(liquidado, comissao):
        raise ComissaoError(
            'Comissão só pode ser incluída quando o valor liquidado for maior ou igual ao valor da comissão.'
        )

    data_contrato = dados.get('data_contrato')
    if isinstance(data_contrato, str) and data_contrato:
        data_contrato = date.fromisoformat(data_contrato)
    elif not isinstance(data_contrato, date):
        data_contrato = None

    return Comissao.objects.create(
        cd_contrato=cd_contrato,
        data_contrato=data_contrato,
        cd_empresa=dados.get('cd_empresa', ''),
        contrato=dados.get('contrato', ''),
        situacao=dados.get('situacao', ''),
        cd_cliente=dados.get('cd_cliente', ''),
        cliente=dados.get('cliente', ''),
        valor_tabela_primeira=_decimal(dados.get('valor_tabela_primeira')),
        valor_tabela_venda=_decimal(dados.get('valor_tabela_venda')),
        valor_venda_a_vista=_decimal(dados.get('valor_venda_a_vista')),
        desconto=_decimal(dados.get('desconto')),
        liquidado=liquidado,
        percentual=float(dados['percentual']) if dados.get('percentual') not in (None, '') else None,
        comissao=comissao,
        data_corte=data_corte,
        mes_fechamento=mes_fechamento,
        ano_fechamento=ano_fechamento,
        data_pagamento=data_pagamento,
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )


def atualizar_data_pagamento(comissao_id: int, data_pagamento: date) -> Comissao:
    if not data_pagamento:
        raise ComissaoError('Informe a data de pagamento.')
    try:
        comissao = Comissao.objects.get(pk=comissao_id)
    except Comissao.DoesNotExist as exc:
        raise ComissaoError('Comissão não encontrada.') from exc
    comissao.data_pagamento = data_pagamento
    comissao.save(update_fields=['data_pagamento'])
    return comissao


def excluir_comissao(comissao_id: int) -> None:
    try:
        comissao = Comissao.objects.get(pk=comissao_id)
    except Comissao.DoesNotExist as exc:
        raise ComissaoError('Comissão não encontrada.') from exc
    comissao.delete()
