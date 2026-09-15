"""Busca de lançamentos e gestão de exceções."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from django.utils.dateparse import parse_date

from controladoria.models import ExcecaoLancamento, RegraMedida, TipoExcecao
from controladoria.services.excecao_dw import ExcecaoDWError, inserir_excecao_dw
from controladoria.services.motor_regras import MotorRegrasError, executar_sql_dw
from controladoria.services.sql_builder import (
    build_regra_lancamentos_count_sql,
    build_regra_lancamentos_sql,
)

PAGE_SIZE = 50


def _row_to_dict(colunas: list[str], linha: tuple) -> dict:
    return {col: linha[i] for i, col in enumerate(colunas)}


def _parse_data(valor) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        return parse_date(valor[:10])
    return None


def _normalizar_str(valor) -> str:
    if valor is None:
        return ''
    return str(valor).strip()


def _normalizar_valor(valor) -> float | None:
    if valor is None or valor == '':
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 4)
    raw = str(valor).strip()
    if not raw:
        return None
    # Suporta formato brasileiro: 1.234,56
    if ',' in raw:
        if '.' in raw:
            raw = raw.replace('.', '').replace(',', '.')
        else:
            raw = raw.replace(',', '.')
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _row_get(row: dict, *nomes: str):
    for nome in nomes:
        if nome in row and row[nome] not in (None, ''):
            return row[nome]
    return None


def lancamento_bate_excecao(row: dict, exc: ExcecaoLancamento) -> bool:
    """
    Verifica se o lançamento corresponde à exceção.
    Mesma regra do SQL: todos os campos preenchidos na exceção devem coincidir.
    """
    criterios: list[bool] = []

    if exc.chave_orc and str(exc.chave_orc).strip():
        chave_row = _normalizar_str(_row_get(row, 'chaveOrc', 'chave_orc'))
        criterios.append(chave_row == str(exc.chave_orc).strip())

    if exc.cd_empresa:
        criterios.append(_normalizar_str(_row_get(row, 'cdEmpresa', 'cd_empresa')) == str(exc.cd_empresa).strip())

    if exc.cd_empreendimento:
        criterios.append(
            _normalizar_str(_row_get(row, 'cdEmpreendimento', 'cd_empreendimento'))
            == str(exc.cd_empreendimento).strip()
        )

    if exc.cd_nucleo:
        criterios.append(_normalizar_str(_row_get(row, 'cdNucleo', 'cd_nucleo')) == str(exc.cd_nucleo).strip())

    if exc.cd_centro:
        criterios.append(_normalizar_str(_row_get(row, 'cdCentro', 'cd_centro')) == str(exc.cd_centro).strip())

    if exc.data:
        criterios.append(_parse_data(_row_get(row, 'Data', 'data')) == exc.data)

    if exc.assunto:
        criterios.append(_normalizar_str(_row_get(row, 'Assunto', 'assunto')) == str(exc.assunto).strip())

    if exc.classificacao:
        criterios.append(
            _normalizar_str(_row_get(row, 'Classificacao', 'classificacao')) == str(exc.classificacao).strip()
        )

    if exc.cliente_fornecedor:
        criterios.append(
            _normalizar_str(_row_get(row, 'ClienteFornecedor', 'cliente_fornecedor'))
            == str(exc.cliente_fornecedor).strip()
        )

    if exc.valor is not None:
        criterios.append(_normalizar_valor(_row_get(row, 'valor')) == _normalizar_valor(exc.valor))

    if not criterios:
        return False

    return all(criterios)


def _obter_excecoes_ativas(regra: RegraMedida) -> list[ExcecaoLancamento]:
    return list(regra.excecoes.filter(ativo=True, tipo=TipoExcecao.EXCLUIR))


def lancamento_ja_excluido(row: dict, excecoes: list[ExcecaoLancamento]) -> bool:
    return any(lancamento_bate_excecao(row, exc) for exc in excecoes)


def obter_regras_medida(medida_id: int) -> list[RegraMedida]:
    return list(
        RegraMedida.objects.filter(medida_id=medida_id, ativo=True)
        .select_related('medida')
        .prefetch_related('excecoes')
        .order_by('nome')
    )


def _periodo_mes_atual() -> tuple[date, date]:
    hoje = date.today()
    ultimo_dia = monthrange(hoje.year, hoje.month)[1]
    return date(hoje.year, hoje.month, 1), date(hoje.year, hoje.month, ultimo_dia)


def _parse_filtros_lancamentos(
    data_inicio_raw: str = '',
    data_fim_raw: str = '',
    status: str = 'todos',
) -> tuple[date, date, str]:
    data_inicio = parse_date(data_inicio_raw) if data_inicio_raw else None
    data_fim = parse_date(data_fim_raw) if data_fim_raw else None
    padrao_inicio, padrao_fim = _periodo_mes_atual()
    if data_inicio is None:
        data_inicio = padrao_inicio
    if data_fim is None:
        data_fim = padrao_fim
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio
    if status not in ('todos', 'ativos', 'excluidos'):
        status = 'todos'
    return data_inicio, data_fim, status


def buscar_lancamentos_regra(
    regra: RegraMedida,
    pagina: int = 1,
    busca: str = '',
    data_inicio: date | None = None,
    data_fim: date | None = None,
    status: str = 'todos',
) -> dict:
    offset = max(pagina - 1, 0) * PAGE_SIZE
    sql = build_regra_lancamentos_sql(
        regra,
        limite=PAGE_SIZE,
        offset=offset,
        busca=busca,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status,
    )
    sql_count = build_regra_lancamentos_count_sql(
        regra,
        busca=busca,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status,
    )

    colunas, linhas = executar_sql_dw(sql)
    _, count_rows = executar_sql_dw(sql_count)
    total = int(count_rows[0][0]) if count_rows else 0

    excecoes = _obter_excecoes_ativas(regra)
    lancamentos = []
    for linha in linhas:
        row = _row_to_dict(colunas, linha)
        lancamentos.append({
            **row,
            'data_fmt': _parse_data(row.get('Data')),
            'ja_excluido': lancamento_ja_excluido(row, excecoes),
        })

    return {
        'lancamentos': lancamentos,
        'colunas': [c for c in colunas if c != 'chaveOrc'],
        'total': total,
        'pagina': pagina,
        'total_paginas': max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        'page_size': PAGE_SIZE,
        'sql': sql,
    }


def criar_excecao_lancamento(regra: RegraMedida, dados: dict, motivo: str = '') -> ExcecaoLancamento:
    row = {
        'chaveOrc': dados.get('chave_orc') or dados.get('chaveOrc'),
        'cdEmpresa': dados.get('cd_empresa') or dados.get('cdEmpresa'),
        'cdEmpreendimento': dados.get('cd_empreendimento') or dados.get('cdEmpreendimento'),
        'cdNucleo': dados.get('cd_nucleo') or dados.get('cdNucleo'),
        'cdCentro': dados.get('cd_centro') or dados.get('cdCentro'),
        'Data': dados.get('data') or dados.get('Data'),
        'Assunto': dados.get('assunto') or dados.get('Assunto'),
        'Classificacao': dados.get('classificacao') or dados.get('Classificacao'),
        'ClienteFornecedor': dados.get('cliente_fornecedor') or dados.get('ClienteFornecedor'),
        'valor': dados.get('valor'),
    }

    excecoes = _obter_excecoes_ativas(regra)
    if lancamento_ja_excluido(row, excecoes):
        raise MotorRegrasError('Este lançamento já está nas exceções.')

    data_lanc = _parse_data(row.get('Data'))
    valor = _normalizar_valor(row.get('valor'))

    exc = ExcecaoLancamento.objects.create(
        regra=regra,
        tipo=TipoExcecao.EXCLUIR,
        chave_orc=_normalizar_str(row.get('chaveOrc')),
        cd_empresa=_normalizar_str(row.get('cdEmpresa')),
        cd_empreendimento=_normalizar_str(row.get('cdEmpreendimento')),
        cd_nucleo=_normalizar_str(row.get('cdNucleo')),
        cd_centro=_normalizar_str(row.get('cdCentro')),
        data=data_lanc,
        assunto=_normalizar_str(row.get('Assunto')),
        classificacao=_normalizar_str(row.get('Classificacao')),
        cliente_fornecedor=_normalizar_str(row.get('ClienteFornecedor')),
        valor=valor,
        motivo=motivo or 'Excluído via tela de exceções',
        ativo=True,
    )

    try:
        inserir_excecao_dw(exc)
    except ExcecaoDWError as exc_err:
        exc.delete()
        raise MotorRegrasError(str(exc_err)) from exc_err

    return exc


def excluir_excecao_lancamento(exc: ExcecaoLancamento) -> None:
    """Remove exceção no app; o signal pre_delete sincroniza o DW."""
    exc.delete()
