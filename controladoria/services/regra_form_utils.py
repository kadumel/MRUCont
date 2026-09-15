"""Conversão entre formulário amigável e JSON armazenado na regra."""

from __future__ import annotations

from controladoria.services.consulta_base import (
    JOIN_DEFINICOES,
    campos_agregacao,
    campos_filtro,
    joins_necessarios_por_campos,
    joins_padrao,
    usa_joins_dim,
)

AGRUPAMENTO_OPCOES = [
    ('cdEmpresa', 'Empresa'),
    ('cdEmpreendimento', 'Empreendimento'),
    ('cdNucleo', 'Núcleo'),
    ('cdCentro', 'Centro'),
    ('mes', 'Mês (competência)'),
]

GROUP_BY_MAP = {
    'cdEmpresa': 'cdEmpresa',
    'cdEmpreendimento': 'cdEmpreendimento',
    'cdNucleo': 'cdNucleo',
    'cdCentro': 'cdCentro',
    'mes': 'eomonth(Data)',
}

OPERADOR_RAIZ_CHOICES = [
    ('or', 'OU — basta um grupo atender'),
    ('and', 'E — todos os grupos devem atender'),
]

SECOES_FILTRO = ('incluir', 'excluir')


def parse_valores_texto(texto: str, operador: str) -> list[str]:
    texto = (texto or '').strip()
    if not texto:
        return []
    if operador in ('in', 'not_in'):
        partes = []
        for linha in texto.split('\n'):
            partes.extend(p.strip() for p in linha.split(',') if p.strip())
        return partes
    return [texto]


def _item_condicao(campo: str, operador: str, valores_txt: str) -> dict | None:
    campo = (campo or '').strip()
    if not campo:
        return None
    valores = parse_valores_texto(valores_txt, operador)
    if not valores:
        return None
    return {
        'campo': campo,
        'operador': operador,
        'valores': valores,
    }


def _bloco_vazio(operador: str = 'and') -> dict:
    return {'operador': operador, 'grupos': []}


def _normalizar_bloco(bloco) -> dict:
    if not isinstance(bloco, dict):
        return _bloco_vazio()
    operador = (bloco.get('operador') or 'and').lower()
    if operador not in ('and', 'or'):
        operador = 'and'
    return {
        'operador': operador,
        'grupos': list(bloco.get('grupos') or []),
    }


def _parse_grupos_post(post_data, secao: str) -> dict:
    operador_raiz = (post_data.get(f'{secao}_operador_raiz') or ('and' if secao == 'incluir' else 'or')).strip().lower()
    if operador_raiz not in ('and', 'or'):
        operador_raiz = 'and' if secao == 'incluir' else 'or'

    try:
        grupo_count = int(post_data.get(f'{secao}_grupo_count') or 0)
    except (TypeError, ValueError):
        grupo_count = 0

    grupos: list[dict] = []
    for idx in range(grupo_count):
        campos = post_data.getlist(f'{secao}_grupo_{idx}_campo')
        operadores = post_data.getlist(f'{secao}_grupo_{idx}_operador')
        valores_list = post_data.getlist(f'{secao}_grupo_{idx}_valores')
        operador_grupo = (post_data.get(f'{secao}_grupo_{idx}_operador_logico') or 'and').strip().lower()
        if operador_grupo not in ('and', 'or'):
            operador_grupo = 'and'

        itens: list[dict] = []
        for campo, operador, valores_txt in zip(campos, operadores, valores_list):
            item = _item_condicao(campo, operador, valores_txt)
            if item:
                itens.append(item)

        if itens:
            grupos.append({
                'operador': operador_grupo,
                'itens': itens,
            })

    return {'operador': operador_raiz, 'grupos': grupos}


def condicoes_from_post(post_data) -> dict:
    """Monta JSON v3 com blocos independentes de incluir e excluir."""
    return {
        'versao': 3,
        'incluir': _parse_grupos_post(post_data, 'incluir'),
        'excluir': _parse_grupos_post(post_data, 'excluir'),
    }


def _itens_de_joins(joins: list | None) -> list[dict]:
    itens: list[dict] = []
    for join in joins or []:
        if join.get('tipo') != 'DimSubGrupo':
            continue
        for filtro in join.get('filtros', []):
            campo = filtro.get('campo', '')
            if 'nmSubGrupo' in campo:
                itens.append({
                    'campo': 'nmSubGrupo',
                    'operador': filtro.get('operador', 'in'),
                    'valores': list(filtro.get('valores', [])),
                })
    return itens


def normalizar_condicoes(condicoes, joins: list | None = None) -> dict:
    """Converte formatos legados para v3 (incluir + excluir)."""
    if isinstance(condicoes, dict) and condicoes.get('versao') == 3:
        return {
            'versao': 3,
            'incluir': _normalizar_bloco(condicoes.get('incluir')),
            'excluir': _normalizar_bloco(condicoes.get('excluir')),
        }

    if isinstance(condicoes, dict) and condicoes.get('versao') == 2:
        bloco = {
            'operador': condicoes.get('operador', 'or'),
            'grupos': list(condicoes.get('grupos') or []),
        }
        if not bloco['grupos'] and joins:
            itens_join = _itens_de_joins(joins)
            if itens_join:
                bloco['grupos'] = [{'operador': 'and', 'itens': itens_join}]
        if condicoes.get('aplicacao') == 'excluir':
            return {'versao': 3, 'incluir': _bloco_vazio('and'), 'excluir': bloco}
        return {'versao': 3, 'incluir': bloco, 'excluir': _bloco_vazio('or')}

    itens = list(condicoes or [])
    itens_join = _itens_de_joins(joins)
    for item_join in itens_join:
        if item_join not in itens:
            itens.append(item_join)

    incluir = _bloco_vazio('and')
    if itens:
        incluir['grupos'] = [{'operador': 'and', 'itens': itens}]

    return {
        'versao': 3,
        'incluir': incluir,
        'excluir': _bloco_vazio('or'),
    }


def _bloco_tem_itens(bloco: dict) -> bool:
    return any(grupo.get('itens') for grupo in bloco.get('grupos', []))


def condicoes_tem_itens(condicoes) -> bool:
    normalizado = normalizar_condicoes(condicoes)
    return _bloco_tem_itens(normalizado['incluir']) or _bloco_tem_itens(normalizado['excluir'])


def _iter_itens_condicoes(normalizado: dict):
    for secao in SECOES_FILTRO:
        for grupo in normalizado.get(secao, {}).get('grupos', []):
            for item in grupo.get('itens', []):
                yield item


def joins_from_condicoes(condicoes) -> list[dict]:
    """Define joins necessários com base nos campos filtrados."""
    if not usa_joins_dim():
        return []

    normalizado = normalizar_condicoes(condicoes)
    joins: list[dict] = list(joins_padrao())
    tipos = {j['tipo'] for j in joins}

    campos_usados: set[str] = set()
    for item in _iter_itens_condicoes(normalizado):
        campos_usados.add(item.get('campo', ''))

    for tipo in joins_necessarios_por_campos(campos_usados):
        if tipo not in tipos:
            joins.append({'tipo': tipo, 'alias': JOIN_DEFINICOES[tipo]['alias_padrao']})
            tipos.add(tipo)

    return joins


def joins_from_form(usar_subgrupo: bool, subgrupos_texto: str) -> list[dict]:
    joins = [{'tipo': 'DimEmpresa', 'alias': 'emp'}]
    if not usar_subgrupo:
        return joins
    valores = parse_valores_texto(subgrupos_texto, 'in')
    if not valores:
        return joins
    joins.append({
        'tipo': 'DimSubGrupo',
        'alias': 'sb',
        'filtros': [{
            'campo': 'trim(nmSubGrupo)',
            'operador': 'in',
            'valores': valores,
        }],
    })
    return joins


def group_by_from_form(agrupamentos: list[str]) -> list[str]:
    resultado = []
    for chave in agrupamentos:
        if chave in GROUP_BY_MAP:
            resultado.append(GROUP_BY_MAP[chave])
    return resultado


def subgrupo_from_joins(joins: list | None) -> tuple[bool, str]:
    if not joins:
        return False, ''
    for join in joins:
        if join.get('tipo') != 'DimSubGrupo':
            continue
        for filtro in join.get('filtros', []):
            if 'nmSubGrupo' in filtro.get('campo', ''):
                valores = filtro.get('valores', [])
                return True, '\n'.join(valores)
    return False, ''


def agrupamentos_from_group_by(group_by: list | None) -> list[str]:
    if not group_by:
        return ['cdEmpresa', 'cdEmpreendimento', 'mes']
    reverse_map = {v: k for k, v in GROUP_BY_MAP.items()}
    resultado = []
    for campo in group_by:
        if campo in reverse_map:
            resultado.append(reverse_map[campo])
        elif campo.lower().startswith('eomonth('):
            resultado.append('mes')
        elif campo in GROUP_BY_MAP:
            resultado.append(campo)
    return resultado


def filtros_padrao() -> dict:
    return {
        'versao': 3,
        'incluir': {
            'operador': 'and',
            'grupos': [{
                'operador': 'and',
                'itens': [{'campo': 'Assunto', 'operador': 'in', 'valores': ['impostos']}],
            }],
        },
        'excluir': _bloco_vazio('or'),
    }


def _rotulo_campo(campo: str) -> str:
    return dict(campos_filtro()).get(campo, campo)


def _resumo_item(item: dict) -> str:
    campo = _rotulo_campo(item.get('campo', ''))
    op = item.get('operador', 'eq')
    vals = ', '.join(str(v) for v in item.get('valores', []))
    if op == 'in':
        return f'{campo} em ({vals})'
    if op == 'not_in':
        return f'{campo} não em ({vals})'
    if op == 'eq':
        return f'{campo} = {vals}'
    if op == 'contains':
        return f'{campo} contém "{vals}"'
    return f'{campo} {op} {vals}'


def _resumo_bloco(bloco: dict) -> str:
    partes_grupo = []
    for grupo in bloco.get('grupos', []):
        itens = [_resumo_item(item) for item in grupo.get('itens', [])]
        if not itens:
            continue
        op = grupo.get('operador', 'and').upper()
        texto = f' {op} '.join(itens)
        if len(itens) > 1:
            texto = f'({texto})'
        partes_grupo.append(texto)
    if not partes_grupo:
        return ''
    op_raiz = bloco.get('operador', 'or').upper()
    return f' {op_raiz} '.join(partes_grupo)


def resumo_regra(regra) -> str:
    cond = normalizar_condicoes(regra.condicoes, regra.joins)
    partes = []

    incluir = _resumo_bloco(cond.get('incluir', {}))
    if incluir:
        partes.append(f'Incluir: {incluir}')

    excluir = _resumo_bloco(cond.get('excluir', {}))
    if excluir:
        partes.append(f'Desconsiderar: {excluir}')

    if regra.ano_minimo:
        partes.append(f'Ano >= {regra.ano_minimo}')

    return ' · '.join(partes) if partes else 'Sem filtros'
