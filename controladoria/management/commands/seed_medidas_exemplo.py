from django.core.management.base import BaseCommand

from controladoria.models import Medida, RegraMedida


MEDIDAS_PADRAO = [
    ('ValorPrincipal', 'Valor Principal', 1),
    ('ValorReajuste', 'Valor Reajuste', 2),
    ('ValorEncargos', 'Valor Encargos', 3),
    ('ValorJuros', 'Valor Juros', 4),
    ('ValorMulta', 'Valor Multa', 5),
    ('ValorDesconto', 'Valor Desconto', 6),
    ('ValorFinanceiro', 'Valor Financeiro', 7),
    ('DevolucaoVendas', 'Devolução de Vendas', 8),
    ('ValorDespBancarias', 'Despesas Bancárias', 9),
    ('ImpostoISS_IPTU', 'Impostos ISS / IPTU', 10),
    ('ImpostoFederais', 'Impostos Federais', 11),
    ('ValorDespRecuperacaoLote', 'Desp. Recuperação Lote', 12),
    ('ValorComissao', 'Comissão', 13),
]

REGRA_IMPOSTO_ISS_IPTU = {
    'nome': 'ISS s/ NF e IPTU — Débito',
    'descricao': 'Exemplo: assunto impostos, subgrupo ISS/IPTU, DC=D',
    'ano_minimo': 2024,
    'funcao_agregacao': 'sum',
    'campo_agregacao': 'valor',
    'condicoes': [
        {'campo': 'Assunto', 'operador': 'in', 'valores': ['impostos']},
        {'campo': 'DC', 'operador': 'eq', 'valores': ['D']},
    ],
    'joins': [
        {
            'tipo': 'DimSubGrupo',
            'alias': 'sb',
            'filtros': [
                {'campo': 'trim(nmSubGrupo)', 'operador': 'in', 'valores': ['ISS s/ NF', 'IPTU']},
            ],
        },
    ],
    'group_by': ['cdEmpresa', 'cdEmpreendimento', 'eomonth(Data)'],
}


class Command(BaseCommand):
    help = 'Cadastra medidas padrão do BI e a regra de exemplo ImpostoISS_IPTU.'

    def handle(self, *args, **options):
        for codigo, nome, ordem in MEDIDAS_PADRAO:
            Medida.objects.update_or_create(
                codigo=codigo,
                defaults={'nome': nome, 'ordem': ordem, 'ativo': True},
            )
        self.stdout.write(self.style.SUCCESS(f'{len(MEDIDAS_PADRAO)} medidas cadastradas/atualizadas.'))

        medida = Medida.objects.get(codigo='ImpostoISS_IPTU')
        regra, created = RegraMedida.objects.update_or_create(
            medida=medida,
            nome=REGRA_IMPOSTO_ISS_IPTU['nome'],
            defaults={
                **REGRA_IMPOSTO_ISS_IPTU,
                'ativo': True,
            },
        )
        acao = 'criada' if created else 'atualizada'
        self.stdout.write(self.style.SUCCESS(f'Regra ImpostoISS_IPTU {acao} (id={regra.id}).'))
        self.stdout.write(
            'Acesse /controladoria/ para preview ou /admin/ para gerenciar exceções e ajustes.'
        )
