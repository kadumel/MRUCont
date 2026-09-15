"""Busca de lançamentos excluídos e criação de ajustes manuais."""

from __future__ import annotations

from controladoria.models import AjusteManual, Medida, RegraMedida, TipoAjuste
from controladoria.services.ajuste_dw import AjusteDWError, inserir_ajuste_dw
from controladoria.services.excecoes import (
    _normalizar_str,
    _normalizar_valor,
    _obter_excecoes_ativas,
    _parse_data,
    _row_get,
    buscar_lancamentos_regra,
    lancamento_ja_excluido,
)
from controladoria.services.motor_regras import MotorRegrasError

TOLERANCIA_VALOR = 0.005


def _formatar_valor(valor: float) -> str:
    return f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def row_referencia_from_ajuste(ajuste: AjusteManual) -> dict:
    """Monta dict de referência para localizar ajustes do mesmo lançamento."""
    return {
        'chave_orc': ajuste.chave_orc,
        'cd_empresa': ajuste.cd_empresa,
        'cd_empreendimento': ajuste.cd_empreendimento,
        'cd_nucleo': ajuste.cd_nucleo,
        'cd_centro': ajuste.cd_centro,
        'data': ajuste.data_original or ajuste.data_lancamento,
        'valor': ajuste.valor_original,
    }


def soma_ajustes_lancamento(
    medida: Medida,
    row: dict,
    *,
    excluir_id: int | None = None,
) -> float:
    """Soma os valores dos ajustes ativos vinculados ao mesmo lançamento."""
    ajustes = AjusteManual.objects.filter(medida=medida, ativo=True)
    if excluir_id:
        ajustes = ajustes.exclude(pk=excluir_id)
    return round(
        sum(ajuste.valor for ajuste in ajustes if _ajuste_bate_lancamento(row, ajuste)),
        4,
    )


def valor_restante_ajustes(valor_original: float | None, soma_atual: float) -> float | None:
    if valor_original is None:
        return None
    return round(float(valor_original) - soma_atual, 4)


def validar_soma_ajustes(
    valor_original: float | None,
    soma_atual: float,
    novo_valor: float,
) -> None:
    """Impede que a soma dos ajustes ultrapasse o valor original do lançamento."""
    if valor_original is None:
        return

    total = round(soma_atual + novo_valor, 4)
    limite = float(valor_original)

    if limite >= 0:
        if total > limite + TOLERANCIA_VALOR:
            restante = max(0.0, limite - soma_atual)
            raise MotorRegrasError(
                f'A soma dos ajustes (R$ {_formatar_valor(total)}) ultrapassa o valor original '
                f'(R$ {_formatar_valor(limite)}). '
                f'Restam R$ {_formatar_valor(restante)} disponíveis para novos ajustes.'
            )
        return

    if total < limite - TOLERANCIA_VALOR:
        restante = min(0.0, limite - soma_atual)
        raise MotorRegrasError(
            f'A soma dos ajustes (R$ {_formatar_valor(total)}) ultrapassa o valor original '
            f'(R$ {_formatar_valor(limite)}). '
            f'Restam R$ {_formatar_valor(restante)} disponíveis para novos ajustes.'
        )


def resumo_ajustes_lancamento(medida: Medida, row: dict) -> dict:
    """Retorna totais de ajustes já vinculados ao lançamento."""
    soma = soma_ajustes_lancamento(medida, row)
    valor_original = _normalizar_valor(_row_get(row, 'valor'))
    return {
        'soma_ajustes': soma,
        'valor_original': valor_original,
        'valor_restante': valor_restante_ajustes(valor_original, soma),
    }


def _ajuste_bate_lancamento(row: dict, ajuste: AjusteManual) -> bool:
    """
    Vincula ajuste ao lançamento usando todos os campos de referência preenchidos
    (mesma regra das exceções — chave_orc sozinha não identifica o lançamento).
    """
    criterios: list[bool] = []

    if ajuste.chave_orc and str(ajuste.chave_orc).strip():
        chave_row = _normalizar_str(_row_get(row, 'chaveOrc', 'chave_orc'))
        criterios.append(chave_row == str(ajuste.chave_orc).strip())

    if ajuste.cd_empresa:
        criterios.append(
            _normalizar_str(_row_get(row, 'cdEmpresa', 'cd_empresa'))
            == str(ajuste.cd_empresa).strip()
        )

    if ajuste.cd_empreendimento:
        criterios.append(
            _normalizar_str(_row_get(row, 'cdEmpreendimento', 'cd_empreendimento'))
            == str(ajuste.cd_empreendimento).strip()
        )

    if ajuste.cd_nucleo:
        criterios.append(
            _normalizar_str(_row_get(row, 'cdNucleo', 'cd_nucleo'))
            == str(ajuste.cd_nucleo).strip()
        )

    if ajuste.cd_centro:
        criterios.append(
            _normalizar_str(_row_get(row, 'cdCentro', 'cd_centro'))
            == str(ajuste.cd_centro).strip()
        )

    data_ref = ajuste.data_original or ajuste.data_lancamento
    if data_ref:
        criterios.append(_parse_data(_row_get(row, 'Data', 'data')) == data_ref)

    if ajuste.valor_original is not None:
        criterios.append(
            _normalizar_valor(_row_get(row, 'valor')) == _normalizar_valor(ajuste.valor_original)
        )

    if not criterios:
        return False

    return all(criterios)


def ajustes_para_lancamento(row: dict, ajustes: list[AjusteManual]) -> list[AjusteManual]:
    return [ajuste for ajuste in ajustes if _ajuste_bate_lancamento(row, ajuste)]


def buscar_lancamentos_excluidos(
    regra: RegraMedida,
    pagina: int = 1,
    busca: str = '',
    data_inicio=None,
    data_fim=None,
) -> dict:
    resultado = buscar_lancamentos_regra(
        regra,
        pagina=pagina,
        busca=busca,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status='excluidos',
    )
    ajustes = list(
        AjusteManual.objects.filter(medida=regra.medida, ativo=True).order_by('-criado_em')
    )
    for lanc in resultado['lancamentos']:
        vinculados = ajustes_para_lancamento(lanc, ajustes)
        lanc['qtd_ajustes'] = len(vinculados)
        lanc['soma_ajustes'] = round(sum(a.valor for a in vinculados), 4)
        valor_original = _normalizar_valor(_row_get(lanc, 'valor'))
        lanc['valor_restante'] = valor_restante_ajustes(valor_original, lanc['soma_ajustes'])
    return resultado


def dados_lancamento_from_request(data) -> dict:
    data_lanc = _parse_data(
        data.get('data') or data.get('data_lancamento') or data.get('data_original')
    )
    valor_ref = data.get('valor_original')
    if valor_ref in (None, ''):
        valor_ref = data.get('valor')
    return {
        'chave_orc': _normalizar_str(data.get('chave_orc') or data.get('chaveOrc')),
        'cd_empresa': _normalizar_str(data.get('cd_empresa') or data.get('cdEmpresa')),
        'cd_empreendimento': _normalizar_str(data.get('cd_empreendimento') or data.get('cdEmpreendimento')),
        'cd_nucleo': _normalizar_str(data.get('cd_nucleo') or data.get('cdNucleo')),
        'cd_centro': _normalizar_str(data.get('cd_centro') or data.get('cdCentro')),
        'data': data_lanc,
        'assunto': _normalizar_str(data.get('assunto') or data.get('Assunto')),
        'classificacao': _normalizar_str(data.get('classificacao') or data.get('Classificacao')),
        'cliente_fornecedor': _normalizar_str(
            data.get('cliente_fornecedor') or data.get('ClienteFornecedor')
        ),
        'valor': _normalizar_valor(valor_ref),
        'dc': _normalizar_str(data.get('dc') or data.get('DC')),
    }


def lancamento_esta_excluido(regra: RegraMedida, row: dict) -> bool:
    excecoes = _obter_excecoes_ativas(regra)
    return lancamento_ja_excluido(row, excecoes) if excecoes else False


def criar_ajuste_lancamento(
    medida: Medida,
    regra: RegraMedida,
    dados: dict,
    observacao: str = '',
) -> AjusteManual:
    row = dados_lancamento_from_request(dados)
    if not lancamento_esta_excluido(regra, row):
        raise MotorRegrasError('Só é possível gerar ajuste para lançamentos excluídos da regra.')

    data_competencia = _parse_data(dados.get('data_competencia'))
    if not data_competencia:
        raise MotorRegrasError('Informe a data do lançamento.')

    valor = _normalizar_valor(dados.get('valor'))
    if valor is None:
        raise MotorRegrasError('Informe o valor do lançamento.')

    if not row.get('cd_empresa'):
        raise MotorRegrasError('Empresa do lançamento não informada.')

    obs = (observacao or '').strip() or (dados.get('observacao') or '').strip()
    obs = obs or f'Ajuste gerado a partir de lançamento excluído ({regra.nome}).'

    data_original = _parse_data(dados.get('data_original')) or row.get('data')
    valor_original = _normalizar_valor(dados.get('valor_original'))
    if valor_original is None:
        valor_original = row.get('valor')

    soma_atual = soma_ajustes_lancamento(medida, row)
    validar_soma_ajustes(valor_original, soma_atual, valor)

    ajuste = AjusteManual.objects.create(
        medida=medida,
        tipo=TipoAjuste.RECLASSIFICACAO,
        cd_empresa=row['cd_empresa'],
        cd_empreendimento=row['cd_empreendimento'],
        cd_nucleo=row['cd_nucleo'],
        cd_centro=row['cd_centro'],
        data_competencia=data_competencia,
        data_lancamento=data_competencia,
        data_original=data_original,
        valor=valor,
        valor_original=valor_original,
        chave_orc=row['chave_orc'],
        observacao=obs,
        ativo=True,
    )

    try:
        inserir_ajuste_dw(ajuste)
    except AjusteDWError as exc_err:
        ajuste.delete()
        raise MotorRegrasError(str(exc_err)) from exc_err

    return ajuste
