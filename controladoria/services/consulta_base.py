"""
Consulta base das regras de medida.

Colunas carregadas automaticamente de [dbo].[VW_Q12_SISTEMA] (ou FONTE_REGRAS_TABELA).
Ao alterar a VIEW no DW, rode: python manage.py sync_campos_view

Ajustes opcionais neste arquivo:
  - CAMPOS_LABEL: rótulos amigáveis
  - CAMPOS_SQL_EXPR: expressão SQL customizada por coluna
  - CAMPOS_EXCLUIDOS: colunas ignoradas
  - CAMPOS_OVERRIDES: flags manuais (filtravel, busca, agregavel...)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

# ---------------------------------------------------------------------------
# Fonte principal — VIEW consolidada no DW
# ---------------------------------------------------------------------------
FATO_TABELA = settings.FONTE_REGRAS_TABELA
FATO_ALIAS = 'f'

TIPOS_TEXTO = frozenset({
    'varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext',
})
TIPOS_NUMERICO = frozenset({
    'int', 'bigint', 'smallint', 'tinyint', 'decimal', 'numeric', 'float', 'real', 'money',
})

# Rótulos amigáveis (opcional — senão usa o nome da coluna)
CAMPOS_LABEL: dict[str, str] = {
    'chaveOrc': 'Conta / Chave',
    'cdEmpresa': 'Código empresa',
    'cdEmpreendimento': 'Código empreendimento',
    'cdNucleo': 'Código núcleo',
    'cdCentro': 'Código centro',
    'Classificacao': 'Classificação',
    'ClienteFornecedor': 'Cliente / Fornecedor',
    'DC': 'D/C (Débito ou Crédito)',
    'cdGrupoCentro': 'Grupo centro',
    'cdSubGrupo': 'Código subgrupo',
    'nmSubGrupo': 'Nome SubGrupo',
    'nmSubgrupo': 'Nome SubGrupo',
    'nmGrupoCentro': 'Nome grupo centro',
    'Segmento': 'Segmento (DimEmpresa)',
    'Q': 'Trimestre (Q)',
    'valor': 'Valor (R$)',
    'siban': 'SIBAN',
    'observacaoDoc': 'Observação documento',
}

# Expressão SQL customizada (opcional)
CAMPOS_SQL_EXPR: dict[str, str] = {
    'nmSubGrupo': f'LTRIM(RTRIM({FATO_ALIAS}.nmSubgrupo))',
    'nmSubgrupo': f'LTRIM(RTRIM({FATO_ALIAS}.nmSubgrupo))',
    'SubGrupo': f'LTRIM(RTRIM({FATO_ALIAS}.nmSubgrupo))',
}

# Colunas ignoradas pelo sistema
CAMPOS_EXCLUIDOS: frozenset[str] = frozenset()

# Alias de filtro (nome lógico → coluna real na VIEW)
CAMPOS_ALIASES: dict[str, str] = {
    'SubGrupo': 'nmSubgrupo',
    'nmSubGrupo': 'nmSubgrupo',
}

# Colunas sempre incluídas na listagem de lançamentos (mesmo antes de sync da VIEW)
COLUNAS_EXTRA_LISTAGEM: tuple[str, ...] = ('siban', 'observacaoDoc')

# Ordem das colunas na tela de exceções (analista)
COLUNAS_TELA_EXCECOES: tuple[str, ...] = (
    'Data', 'cdEmpresa', 'cdEmpreendimento', 'Assunto', 'Classificacao',
    'ClienteFornecedor', 'DC', 'valor', 'siban', 'observacaoDoc', 'nmSubgrupo',
)

# Fallback offline / sem DW (testes)
CAMPOS_FALLBACK: tuple[str, ...] = (
    'chaveOrc', 'Data', 'cdEmpresa', 'cdEmpreendimento', 'cdNucleo', 'cdCentro',
    'Assunto', 'Classificacao', 'ClienteFornecedor', 'DC', 'valor',
    'nmSubGrupo', 'Segmento', 'siban', 'observacaoDoc',
)

_campos_cache: tuple['CampoConsulta', ...] | None = None
_campos_cache_origem: str = 'pendente'


# Flags manuais por coluna (sobrescreve inferência)
CAMPOS_OVERRIDES: dict[str, dict] = {
    'observacaoDoc': {'busca': True},
}


def usa_joins_dim() -> bool:
    return bool(getattr(settings, 'FONTE_REGRAS_USAR_JOINS', False))


def auto_campos_habilitado() -> bool:
    return bool(getattr(settings, 'FONTE_REGRAS_AUTO_CAMPOS', True))


JOIN_DEFINICOES = {
    'DimEmpresa': {
        'tabela': f'[{settings.DATABASE_SCHEMA_DW}].[DimEmpresa]',
        'alias_padrao': 'emp',
        'on': 'emp.cdEmpresa = f.cdEmpresa',
        'sempre': True,
    },
    'DimSubGrupo': {
        'tabela': f'[{settings.DATABASE_SCHEMA_DW}].[DimSubGrupo]',
        'alias_padrao': 'sb',
        'on': 'sb.cdSubGrupo = f.cdSubGrupo',
        'sempre': False,
    },
}


@dataclass(frozen=True)
class CampoConsulta:
    id: str
    label: str
    sql: str
    origem: str = 'fato'
    filtravel: bool = False
    listagem: bool = False
    agregavel: bool = False
    busca: bool = False
    join: str | None = None
    tipo_sql: str = ''


def _dw_disponivel() -> bool:
    return 'dw' in connections.databases


def _quote_coluna(nome: str) -> str:
    if nome.isidentifier():
        return f'{FATO_ALIAS}.{nome}'
    return f'{FATO_ALIAS}.[{nome}]'


def _expr_sql_coluna(nome: str) -> str:
    if usa_joins_dim():
        if nome in ('nmSubGrupo', 'SubGrupo'):
            return 'LTRIM(RTRIM(sb.nmSubGrupo))'
        if nome == 'Segmento':
            return 'emp.Segmento'
    if nome in CAMPOS_SQL_EXPR:
        return CAMPOS_SQL_EXPR[nome]
    return _quote_coluna(nome)


def _label_coluna(nome: str) -> str:
    return CAMPOS_LABEL.get(nome, nome)


def _inferir_flags(nome: str, data_type: str) -> dict:
    tipo = (data_type or '').lower()
    overrides = CAMPOS_OVERRIDES.get(nome, {})

    filtravel = overrides.get('filtravel', nome not in CAMPOS_EXCLUIDOS)
    listagem = overrides.get('listagem', True)
    agregavel = overrides.get('agregavel', nome == 'valor' or tipo in TIPOS_NUMERICO and nome.startswith('vl'))
    busca = overrides.get(
        'busca',
        tipo in TIPOS_TEXTO and nome in {
            'chaveOrc', 'Assunto', 'Classificacao', 'ClienteFornecedor', 'cdEmpresa',
        },
    )

    join = None
    if usa_joins_dim():
        if nome in ('nmSubGrupo', 'SubGrupo') or 'SubGrupo' in nome:
            join = 'DimSubGrupo'
        elif nome == 'Segmento':
            join = 'DimEmpresa'

    return {
        'filtravel': filtravel,
        'listagem': listagem,
        'agregavel': agregavel,
        'busca': busca,
        'join': join,
    }


def _campo_from_coluna(nome: str, data_type: str = 'varchar') -> CampoConsulta:
    flags = _inferir_flags(nome, data_type)
    return CampoConsulta(
        id=nome,
        label=_label_coluna(nome),
        sql=_expr_sql_coluna(nome),
        origem='dim' if flags['join'] else 'fato',
        filtravel=flags['filtravel'],
        listagem=flags['listagem'],
        agregavel=flags['agregavel'],
        busca=flags['busca'],
        join=flags['join'],
        tipo_sql=data_type,
    )


def _carregar_colunas_dw() -> list[tuple[str, str]]:
    schema = settings.DATABASE_SCHEMA_DW
    tabela = FATO_TABELA
    sql = """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """
    with connections['dw'].cursor() as cursor:
        cursor.execute(sql, [schema, tabela])
        return [(row[0], row[1]) for row in cursor.fetchall()]


def _montar_campos(colunas: list[tuple[str, str]]) -> tuple[CampoConsulta, ...]:
    campos: list[CampoConsulta] = []
    ids: set[str] = set()

    for nome, data_type in colunas:
        if nome in CAMPOS_EXCLUIDOS:
            continue
        campo = _campo_from_coluna(nome, data_type)
        campos.append(campo)
        ids.add(nome)

    for alias_id, destino in CAMPOS_ALIASES.items():
        if alias_id in ids or destino not in ids:
            continue
        base = _campos_por_id_dict(campos).get(destino)
        if not base:
            continue
        campos.append(replace(
            base,
            id=alias_id,
            label=_label_coluna(alias_id),
            sql=_expr_sql_coluna(alias_id),
        ))

    return tuple(campos)


def _campos_por_id_dict(campos: list[CampoConsulta]) -> dict[str, CampoConsulta]:
    return {c.id: c for c in campos}


def _campos_fallback() -> tuple[CampoConsulta, ...]:
    return _montar_campos([(nome, 'varchar') for nome in CAMPOS_FALLBACK])


def get_campos_consulta(force_refresh: bool = False) -> tuple[CampoConsulta, ...]:
    """Retorna colunas da VIEW (cache em memória)."""
    global _campos_cache, _campos_cache_origem

    if _campos_cache is not None and not force_refresh:
        return _campos_cache

    if auto_campos_habilitado() and _dw_disponivel():
        try:
            colunas = _carregar_colunas_dw()
            if colunas:
                _campos_cache = _montar_campos(colunas)
                _campos_cache_origem = f'dw:{FATO_TABELA}'
                return _campos_cache
        except OperationalError:
            pass

    _campos_cache = _campos_fallback()
    _campos_cache_origem = 'fallback'
    return _campos_cache


def origem_campos_consulta() -> str:
    get_campos_consulta()
    return _campos_cache_origem


def limpar_cache_campos() -> None:
    global _campos_cache, _campos_cache_origem
    _campos_cache = None
    _campos_cache_origem = 'pendente'


def _campos_por_id() -> dict[str, CampoConsulta]:
    return {c.id: c for c in get_campos_consulta()}


def fato_sql() -> str:
    return f'[{settings.DATABASE_SCHEMA_DW}].[{FATO_TABELA}]'


def campos_filtro() -> list[tuple[str, str]]:
    return [(c.id, c.label) for c in get_campos_consulta() if c.filtravel]


def campos_agregacao() -> list[tuple[str, str]]:
    agregaveis = [c for c in get_campos_consulta() if c.agregavel]
    if not agregaveis:
        return [('valor', 'Valor (R$)')]
    return [(c.id, c.label) for c in agregaveis]


def colunas_listagem(joins_ativos: set[str] | None = None) -> list[tuple[str, str]]:
    joins_ativos = joins_ativos or set()
    colunas: list[tuple[str, str]] = []
    for campo in get_campos_consulta():
        if not campo.listagem:
            continue
        if usa_joins_dim() and campo.join and campo.join not in joins_ativos:
            continue
        colunas.append((campo.sql, campo.id))

    aliases = {alias for _, alias in colunas}
    aliases_lower = {alias.lower() for alias in aliases}
    for extra in COLUNAS_EXTRA_LISTAGEM:
        if extra.lower() in aliases_lower:
            continue
        colunas.append((_expr_sql_coluna(extra), extra))
    return colunas


def metadados_colunas_tela(ids: tuple[str, ...]) -> list[dict]:
    """Metadados para renderizar colunas em templates de lançamentos."""
    por_id = _campos_por_id()
    por_id_lower = {k.lower(): v for k, v in por_id.items()}
    resultado: list[dict] = []

    for col_id in ids:
        meta = por_id.get(col_id) or por_id_lower.get(col_id.lower())
        if col_id == 'nmSubgrupo' and not meta:
            meta = por_id.get('nmSubGrupo') or por_id_lower.get('nmsubgrupo')
        resultado.append({
            'id': col_id,
            'label': meta.label if meta else _label_coluna(col_id),
            'truncate': 45 if col_id.lower() == 'observacaodoc' else 30,
        })
    return resultado


def colunas_tela_excecoes() -> list[dict]:
    """Colunas visíveis na tela de exceções."""
    ids = list(COLUNAS_TELA_EXCECOES)
    if not campo_na_listagem('nmSubGrupo') and not campo_na_listagem('nmSubgrupo'):
        ids = [i for i in ids if i.lower() != 'nmsubgrupo']
    return metadados_colunas_tela(tuple(ids))


def campo_na_listagem(campo_id: str) -> bool:
    por_id = _campos_por_id()
    if campo_id in por_id:
        return bool(por_id[campo_id].listagem)
    destino = CAMPOS_ALIASES.get(campo_id)
    if destino and destino in por_id:
        return bool(por_id[destino].listagem)
    campo_lower = campo_id.lower()
    for chave, meta in por_id.items():
        if chave.lower() == campo_lower:
            return bool(meta.listagem)
    return False


def joins_padrao() -> list[dict]:
    if not usa_joins_dim():
        return []
    return [
        {'tipo': tipo, 'alias': cfg['alias_padrao']}
        for tipo, cfg in JOIN_DEFINICOES.items()
        if cfg.get('sempre')
    ]


def joins_necessarios_por_campos(campos: set[str]) -> list[str]:
    if not usa_joins_dim():
        return []
    por_id = _campos_por_id()
    joins: list[str] = []
    for campo_id in campos:
        real_id = CAMPOS_ALIASES.get(campo_id, campo_id)
        meta = por_id.get(real_id) or por_id.get(campo_id)
        if meta and meta.join and meta.join not in joins:
            joins.append(meta.join)
    return joins


def join_requer_subgrupo(campo_id: str) -> bool:
    if not usa_joins_dim():
        return False
    real_id = CAMPOS_ALIASES.get(campo_id, campo_id)
    meta = _campos_por_id().get(real_id) or _campos_por_id().get(campo_id)
    if not meta:
        return 'SubGrupo' in campo_id or campo_id == 'cdSubGrupo'
    return meta.join == 'DimSubGrupo' or 'SubGrupo' in campo_id


def resolver_campo_sql(campo_id: str) -> str | None:
    campo_id = (campo_id or '').strip()
    por_id = _campos_por_id()
    meta = por_id.get(campo_id)
    if meta:
        return meta.sql
    real_id = CAMPOS_ALIASES.get(campo_id)
    if real_id and real_id in por_id:
        return por_id[real_id].sql
    return None


def clausula_busca_texto(busca: str, escapar_fn) -> str:
    partes = []
    for campo in get_campos_consulta():
        if not campo.busca:
            continue
        expr = campo.sql
        if 'chaveOrc' in campo.id or 'chaveOrc' in expr:
            expr = f'CAST({FATO_ALIAS}.chaveOrc AS NVARCHAR(MAX))'
        partes.append(f"{expr} LIKE '%{escapar_fn(busca)}%'")
    if not partes:
        esc = escapar_fn(busca)
        return (
            f"(CAST({FATO_ALIAS}.chaveOrc AS NVARCHAR(MAX)) LIKE '%{esc}%'"
            f" OR {FATO_ALIAS}.Assunto LIKE '%{esc}%')"
        )
    return '(' + ' OR '.join(partes) + ')'


def sql_consulta_base_preview() -> str:
    if usa_joins_dim():
        joins = [
            f"JOIN {cfg['tabela']} {cfg['alias_padrao']} ON {cfg['on']}"
            for cfg in JOIN_DEFINICOES.values()
            if cfg.get('sempre') or cfg.get('tabela', '').endswith('DimSubGrupo')
        ]
        join_clause = '\n'.join(joins)
        cols = colunas_listagem({'DimEmpresa', 'DimSubGrupo'})
    else:
        join_clause = '-- joins incluídos na VIEW'
        cols = colunas_listagem()

    select_cols = ',\n    '.join(f'{expr} AS [{alias}]' for expr, alias in cols)
    return f"""SELECT
    {select_cols}
FROM {fato_sql()} {FATO_ALIAS}
{join_clause}
WHERE
    YEAR({FATO_ALIAS}.Data) >= @ano_minimo
-- + filtros da regra (incluir / desconsiderar)
-- + exceções / ajustes""".strip()
