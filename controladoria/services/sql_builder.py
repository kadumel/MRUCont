"""Construção de SQL para execução das regras de medida."""

from __future__ import annotations

from django.conf import settings

from controladoria.models import Medida
from controladoria.services.consulta_base import (
    FATO_ALIAS,
    JOIN_DEFINICOES,
    clausula_busca_texto,
    colunas_listagem,
    fato_sql,
    joins_necessarios_por_campos,
    joins_padrao,
    resolver_campo_sql,
    usa_joins_dim,
)
from controladoria.services.regra_form_utils import normalizar_condicoes

OPERADORES_SQL = {
    'eq': '=',
    'neq': '<>',
    'in': 'IN',
    'not_in': 'NOT IN',
    'contains': 'LIKE',
    'gt': '>',
    'lt': '<',
    'gte': '>=',
    'lte': '<=',
}

def _escapar_valor(valor) -> str:
    if valor is None:
        return 'NULL'
    if isinstance(valor, bool):
        return '1' if valor else '0'
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def _cast_texto_sql(campo: str) -> str:
    """SQL Server não permite comparar colunas TEXT com VARCHAR diretamente."""
    if 'chaveOrc' in campo and 'CAST(' not in campo.upper():
        return f'CAST({campo} AS NVARCHAR(MAX))'
    return campo


def _renderizar_condicao(campo: str, operador: str, valores: list) -> str:
    campo = _cast_texto_sql(campo)
    op = OPERADORES_SQL.get(operador, '=')

    if operador == 'contains':
        valor = valores[0] if valores else ''
        return f"{campo} LIKE '%{_escapar_valor(valor).strip("'")}%'"

    if operador in ('in', 'not_in'):
        lista = ', '.join(_escapar_valor(v) for v in valores)
        return f'{campo} {op} ({lista})'

    valor = valores[0] if valores else None
    return f'{campo} {op} {_escapar_valor(valor)}'


def _normalizar_campo(campo: str, prefixo_alias: str) -> str:
    campo = campo.strip()
    if campo.lower().startswith('trim('):
        inner = campo[5:-1].strip()
        if '.' not in inner:
            inner = f'{prefixo_alias}.{inner}'
        return f'LTRIM(RTRIM({inner}))'
    if campo.lower().startswith('eomonth('):
        return 'EOMONTH(f.Data)'
    if campo.lower().startswith('year('):
        return f'YEAR(f.Data)'
    if '.' not in campo and not campo.startswith(('LTRIM', 'YEAR', 'EOMONTH')):
        return f'{prefixo_alias}.{campo}'
    return campo


def _resolver_campo_sql(campo_raw: str) -> str:
    campo = (campo_raw or '').strip()
    resolvido = resolver_campo_sql(campo)
    if resolvido:
        return resolvido
    if campo.lower().startswith('trim(') and 'nmsubgrupo' in campo.lower():
        if usa_joins_dim():
            return 'LTRIM(RTRIM(sb.nmSubGrupo))'
        return f'LTRIM(RTRIM({FATO_ALIAS}.nmSubgrupo))'
    return _normalizar_campo(campo, FATO_ALIAS)


def _renderizar_filtros(filtros: list, prefixo_alias: str = 'f') -> list[str]:
    clausulas = []
    for filtro in filtros:
        campo_raw = filtro.get('campo', '')
        if not campo_raw:
            continue
        campo = _normalizar_campo(campo_raw, prefixo_alias)
        operador = filtro.get('operador', 'eq')
        valores = filtro.get('valores', [])
        if not isinstance(valores, list):
            valores = [valores]
        clausulas.append(_renderizar_condicao(campo, operador, valores))
    return clausulas


def _renderizar_joins(joins: list) -> tuple[list[str], list[str]]:
    join_sql: list[str] = []
    filtros_join: list[str] = []
    joins_emitidos: set[str] = set()

    for join in joins:
        tipo = join.get('tipo')
        definicao = JOIN_DEFINICOES.get(tipo)
        if not definicao:
            continue
        alias = join.get('alias', definicao['alias_padrao'])
        chave = f'{tipo}:{alias}'
        if chave not in joins_emitidos:
            on = join.get('on', definicao['on'])
            tabela = definicao['tabela']
            join_sql.append(f'JOIN {tabela} {alias} ON {on}')
            joins_emitidos.add(chave)
        prefixo = alias if alias else 'f'
        filtros_join.extend(_renderizar_filtros(join.get('filtros', []), prefixo_alias=prefixo))
    return join_sql, filtros_join


def _joins_necessarios(regra) -> list[dict]:
    if not usa_joins_dim():
        return []

    joins: list[dict] = list(joins_padrao())
    tipos = {j['tipo'] for j in joins}

    campos_usados: set[str] = set()
    cond = normalizar_condicoes(regra.condicoes, regra.joins)
    for secao in ('incluir', 'excluir'):
        for grupo in cond.get(secao, {}).get('grupos', []):
            for item in grupo.get('itens', []):
                campos_usados.add(item.get('campo', ''))

    for tipo in joins_necessarios_por_campos(campos_usados):
        if tipo not in tipos:
            joins.append({'tipo': tipo, 'alias': JOIN_DEFINICOES[tipo]['alias_padrao']})
            tipos.add(tipo)

    for join in regra.joins or []:
        tipo = join.get('tipo')
        if tipo and tipo not in tipos:
            joins.append(join)
            tipos.add(tipo)

    return joins


def _renderizar_bloco_grupos(bloco: dict) -> str:
    grupos_sql = [_renderizar_grupo_condicoes(grupo) for grupo in bloco.get('grupos', [])]
    grupos_sql = [sql for sql in grupos_sql if sql]
    if not grupos_sql:
        return ''

    op_raiz = bloco.get('operador', 'or').upper()
    if len(grupos_sql) == 1:
        return grupos_sql[0]
    return f"({f' {op_raiz} '.join(grupos_sql)})"


def _renderizar_condicoes_regra(regra) -> list[str]:
    cond = normalizar_condicoes(regra.condicoes, regra.joins)
    partes: list[str] = []

    incluir_sql = _renderizar_bloco_grupos(cond.get('incluir', {}))
    if incluir_sql:
        partes.append(incluir_sql)

    excluir_sql = _renderizar_bloco_grupos(cond.get('excluir', {}))
    if excluir_sql:
        partes.append(f'NOT ({excluir_sql})')

    return partes


def _renderizar_grupo_condicoes(grupo: dict) -> str:
    itens_sql: list[str] = []
    for item in grupo.get('itens', []):
        campo_sql = _resolver_campo_sql(item.get('campo', ''))
        operador = item.get('operador', 'eq')
        valores = item.get('valores', [])
        if not isinstance(valores, list):
            valores = [valores]
        itens_sql.append(_renderizar_condicao(campo_sql, operador, valores))

    if not itens_sql:
        return ''

    op = grupo.get('operador', 'and').upper()
    if len(itens_sql) == 1:
        return itens_sql[0]
    return f"({f' {op} '.join(itens_sql)})"


def _renderizar_group_by(group_by: list) -> tuple[list[str], list[str]]:
    select_cols = []
    group_cols = []
    for campo in group_by:
        expr = campo
        alias = campo
        if campo.lower().startswith('eomonth('):
            alias = 'data'
            expr = f'EOMONTH(f.Data)'
        elif campo.lower().startswith('year('):
            alias = 'ano'
            expr = f'YEAR(f.{campo[5:-1] if campo.endswith(")") else "Data"})'
        elif '.' not in campo:
            expr = f'f.{campo}'
            alias = campo
        select_cols.append(f'{expr} AS [{alias}]')
        group_cols.append(expr)
    return select_cols, group_cols


def _subquery_excecao_lancamento(regra) -> str:
    """Corpo EXISTS/NOT EXISTS para match de exceções no DW."""
    tabela = f'[{settings.DATABASE_SCHEMA_DW}].[FatoExcecaoLancamento]'
    return f"""SELECT 1
    FROM {tabela} ex
    WHERE ex.ativo = 1
      AND ex.tipo = 'excluir'
      AND ex.id_regra = {regra.id}
      AND (NULLIF(ex.chave_orc, '') IS NULL OR CAST(f.chaveOrc AS NVARCHAR(MAX)) = ex.chave_orc)
      AND (NULLIF(ex.cd_empresa, '') IS NULL OR f.cdEmpresa = ex.cd_empresa)
      AND (NULLIF(ex.cd_empreendimento, '') IS NULL OR f.cdEmpreendimento = ex.cd_empreendimento)
      AND (NULLIF(ex.cd_nucleo, '') IS NULL OR f.cdNucleo = ex.cd_nucleo)
      AND (NULLIF(ex.cd_centro, '') IS NULL OR f.cdCentro = ex.cd_centro)
      AND (ex.[data] IS NULL OR CAST(f.Data AS DATE) = ex.[data])
      AND (NULLIF(ex.assunto, '') IS NULL OR f.Assunto = ex.assunto)
      AND (NULLIF(ex.classificacao, '') IS NULL OR f.Classificacao = ex.classificacao)
      AND (NULLIF(ex.cliente_fornecedor, '') IS NULL OR f.ClienteFornecedor = ex.cliente_fornecedor)
      AND (ex.valor IS NULL OR f.valor = ex.valor)"""


def _renderizar_not_exists_excecoes(regra) -> str:
    """Exclusões via tabela FatoExcecaoLancamento no DW."""
    if not regra.pk:
        return ''
    return f'AND NOT EXISTS (\n    {_subquery_excecao_lancamento(regra)}\n)'


def _renderizar_filtro_status_lancamentos(regra, status: str) -> str:
    if not regra.pk or status in ('', 'todos'):
        return ''
    corpo = _subquery_excecao_lancamento(regra)
    if status == 'excluidos':
        return f'AND EXISTS (\n    {corpo}\n)'
    if status == 'ativos':
        return f'AND NOT EXISTS (\n    {corpo}\n)'
    return ''


def _renderizar_filtros_data(data_inicio=None, data_fim=None) -> list[str]:
    clausulas = []
    if data_inicio:
        clausulas.append(f"CAST(f.Data AS DATE) >= {_escapar_valor(data_inicio.isoformat())}")
    if data_fim:
        clausulas.append(f"CAST(f.Data AS DATE) <= {_escapar_valor(data_fim.isoformat())}")
    return clausulas


def _build_regra_clausulas(regra, excecoes=None, aplicar_exclusoes: bool = True) -> tuple[str, list[str], list[str], str]:
    """Retorna fato, joins_sql, where_parts e cláusula de exclusões."""
    fato = fato_sql()
    joins_config = _joins_necessarios(regra)
    joins_sql, filtros_join = _renderizar_joins(joins_config)
    clausulas_condicoes = _renderizar_condicoes_regra(regra)

    where_parts = [f'YEAR(f.Data) >= {regra.ano_minimo}']
    where_parts.extend(clausulas_condicoes)
    where_parts.extend(filtros_join)
    if regra.sql_extra.strip():
        extra = regra.sql_extra.strip()
        if extra.upper().startswith('AND '):
            extra = extra[4:].strip()
        where_parts.append(extra)

    exclusoes = ''
    if aplicar_exclusoes and regra.pk:
        exclusoes = _renderizar_not_exists_excecoes(regra)

    return fato, joins_sql, where_parts, exclusoes


def medidas_ordenadas_codigos() -> list[str]:
    """Códigos das medidas ativas na ordem de cadastro (campo ordem)."""
    return list(
        Medida.objects.filter(ativo=True).order_by('ordem', 'codigo').values_list('codigo', flat=True)
    )


def _renderizar_colunas_medidas(
    codigo_ativo: str,
    funcao: str,
    campo_agreg: str,
    medidas: list[str] | None = None,
) -> list[str]:
    """
    Colunas das medidas no padrão BI: 0 para as demais e agregação na medida da regra.
    """
    medidas = medidas or medidas_ordenadas_codigos()
    if not medidas:
        return [f'{funcao}({campo_agreg}) AS [{codigo_ativo}]']

    colunas: list[str] = []
    for codigo in medidas:
        if codigo == codigo_ativo:
            colunas.append(f'{funcao}({campo_agreg}) AS [{codigo}]')
        else:
            colunas.append(f'0 AS [{codigo}]')
    return colunas


def build_regra_sql(regra, medidas_ordenadas: list[str] | None = None) -> str:
    """Monta SELECT agregado para uma regra de medida."""
    codigo_medida = regra.medida.codigo
    funcao = regra.funcao_agregacao.upper()
    campo_agreg = f'f.{regra.campo_agregacao}'

    select_dims, group_dims = _renderizar_group_by(regra.group_by or ['cdEmpresa', 'cdEmpreendimento', 'eomonth(Data)'])
    fato, joins_sql, where_parts, exclusoes = _build_regra_clausulas(regra)
    colunas_medidas = _renderizar_colunas_medidas(
        codigo_ativo=codigo_medida,
        funcao=funcao,
        campo_agreg=campo_agreg,
        medidas=medidas_ordenadas,
    )

    select_clause = ',\n    '.join(select_dims + colunas_medidas)
    join_clause = '\n'.join(joins_sql)
    where_clause = '\n    AND '.join(where_parts)
    group_clause = ',\n    '.join(group_dims)

    sql = f"""SELECT
    {select_clause}
FROM {fato} f
{join_clause}
WHERE
    {where_clause}
    {exclusoes}
GROUP BY
    {group_clause}"""
    return sql.strip()


COLUNAS_LANCAMENTO = colunas_listagem({'DimEmpresa', 'DimSubGrupo'})


def _clausula_busca(busca: str) -> str:
    esc = busca.strip().replace("'", "''")
    return clausula_busca_texto(esc, lambda valor: valor)


def build_regra_lancamentos_sql(
    regra,
    limite: int = 50,
    offset: int = 0,
    busca: str = '',
    aplicar_exclusoes: bool = False,
    data_inicio=None,
    data_fim=None,
    status: str = 'todos',
) -> str:
    """SELECT de lançamentos individuais (sem agregação) para tela de exceções."""
    fato, joins_sql, where_parts, exclusoes = _build_regra_clausulas(
        regra, aplicar_exclusoes=aplicar_exclusoes,
    )

    where_parts.extend(_renderizar_filtros_data(data_inicio, data_fim))

    if busca.strip():
        where_parts.append(_clausula_busca(busca))

    filtro_status = _renderizar_filtro_status_lancamentos(regra, status)

    joins_ativos = {j.get('tipo') for j in _joins_necessarios(regra)}
    cols = [f'{expr} AS [{alias}]' for expr, alias in colunas_listagem(joins_ativos)]

    join_clause = '\n'.join(joins_sql)
    where_clause = '\n    AND '.join(where_parts)

    return f"""SELECT
    {',\n    '.join(cols)}
FROM {fato} f
{join_clause}
WHERE
    {where_clause}
    {exclusoes}
    {filtro_status}
ORDER BY f.Data DESC, f.cdEmpresa, f.valor
OFFSET {offset} ROWS FETCH NEXT {limite} ROWS ONLY""".strip()


def build_regra_lancamentos_count_sql(
    regra,
    busca: str = '',
    aplicar_exclusoes: bool = False,
    data_inicio=None,
    data_fim=None,
    status: str = 'todos',
) -> str:
    fato, joins_sql, where_parts, exclusoes = _build_regra_clausulas(
        regra, aplicar_exclusoes=aplicar_exclusoes,
    )
    where_parts.extend(_renderizar_filtros_data(data_inicio, data_fim))
    if busca.strip():
        where_parts.append(_clausula_busca(busca))
    filtro_status = _renderizar_filtro_status_lancamentos(regra, status)
    join_clause = '\n'.join(joins_sql)
    where_clause = '\n    AND '.join(where_parts)
    return f"""SELECT COUNT(*) AS total
FROM {fato} f
{join_clause}
WHERE
    {where_clause}
    {exclusoes}
    {filtro_status}""".strip()


def build_consulta_bi(medidas_com_sql: list[tuple[str, str]], group_by: list | None = None) -> str:
    """
    Monta consulta consolidada estilo BI com CTE por regra e SELECT externo contendo
    todas as medidas ativas na ordem de cadastro (0 quando sem regra ou sem valor).
    medidas_com_sql: [(codigo, sql_da_regra), ...]
    """
    if not medidas_com_sql:
        return '-- Nenhuma medida ativa configurada.'

    ctes = []
    for idx, (_, sql) in enumerate(medidas_com_sql):
        ctes.append(f'regra_{idx} AS (\n{sql}\n)')

    dims = group_by or ['cdEmpresa', 'cdEmpreendimento', 'data']
    num_regras = len(medidas_com_sql)

    dim_select_parts = []
    for dim in dims:
        refs = [f'r{idx}.[{dim}]' for idx in range(num_regras)]
        if num_regras == 1:
            dim_select_parts.append(f'{refs[0]}')
        else:
            dim_select_parts.append(f'COALESCE({", ".join(refs)}) AS [{dim}]')
    dim_select = ',\n    '.join(dim_select_parts)

    medidas_ordem = medidas_ordenadas_codigos()

    colunas_medida = []
    for codigo in medidas_ordem:
        refs = [f'r{idx}.[{codigo}]' for idx in range(num_regras)]
        if num_regras == 1:
            colunas_medida.append(f'COALESCE({refs[0]}, 0) AS [{codigo}]')
        else:
            soma = ' + '.join(f'COALESCE({ref}, 0)' for ref in refs)
            colunas_medida.append(f'({soma}) AS [{codigo}]')

    from_base = 'regra_0 r0'
    joins = []
    for idx in range(1, num_regras):
        alias = f'r{idx}'
        on = ' AND '.join(f'r0.[{d}] = {alias}.[{d}]' for d in dims)
        joins.append(f'FULL OUTER JOIN regra_{idx} {alias} ON {on}')

    sql = f"""WITH {',\n'.join(ctes)}
SELECT
    {dim_select},
    {',\n    '.join(colunas_medida)}
FROM {from_base}
{' '.join(joins)}"""
    return sql
