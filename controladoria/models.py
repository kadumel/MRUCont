"""Modelos de configuração: medidas, regras, exceções e ajustes manuais."""

from django.core.exceptions import ValidationError
from django.db import models


class SegmentoEmpresa(models.TextChoices):
    SPE = 'SPE', 'SPE'
    CON = 'CON', 'CON'


class Empresa(models.Model):
    empresa = models.CharField(
        max_length=3,
        unique=True,
        help_text='Código único da empresa (até 3 caracteres).',
    )
    nome = models.CharField(max_length=100, default='')
    segmento = models.CharField(max_length=3, choices=SegmentoEmpresa.choices)
    percentual_venda = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Percentual de venda (0 a 100).',
    )

    class Meta:
        ordering = ['empresa']
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

    def __str__(self):
        return f'{self.empresa} — {self.nome}'


class Socio(models.Model):
    """Cadastro de sócios."""

    nome = models.CharField(max_length=150)
    documento = models.CharField(
        max_length=18,
        blank=True,
        help_text='CPF ou CNPJ (opcional).',
    )
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Sócio'
        verbose_name_plural = 'Sócios'

    def __str__(self):
        return self.nome


class SocioEmpresa(models.Model):
    """Relaciona um sócio a uma empresa com percentual e taxa de administração."""

    socio = models.ForeignKey(
        Socio,
        on_delete=models.CASCADE,
        related_name='empresas',
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='socios',
    )
    percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Percentual de participação na empresa (0 a 100).',
    )
    taxa_administracao = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Taxa de administração (0 a 100).',
    )

    class Meta:
        ordering = ['empresa__empresa', 'socio__nome']
        verbose_name = 'Sócio × Empresa'
        verbose_name_plural = 'Sócios × Empresas'
        constraints = [
            models.UniqueConstraint(
                fields=['socio', 'empresa'],
                name='uniq_socio_empresa',
            ),
        ]

    def __str__(self):
        return f'{self.socio} — {self.empresa} ({self.percentual}%)'

    def clean(self):
        erros = {}
        if self.percentual is not None and (self.percentual < 0 or self.percentual > 100):
            erros['percentual'] = 'O percentual deve estar entre 0 e 100.'
        if self.taxa_administracao is not None and (
            self.taxa_administracao < 0 or self.taxa_administracao > 100
        ):
            erros['taxa_administracao'] = 'A taxa de administração deve estar entre 0 e 100.'
        if erros:
            raise ValidationError(erros)


class Medida(models.Model):
    """Coluna de saída do BI (ex.: ImpostoISS_IPTU, ValorPrincipal)."""

    codigo = models.CharField(
        max_length=80,
        unique=True,
        help_text='Nome da coluna na consulta BI. Ex.: ImpostoISS_IPTU',
    )
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordem', 'codigo']
        verbose_name = 'Medida'
        verbose_name_plural = 'Medidas'

    @property
    def rotulo(self) -> str:
        """Texto único para exibição, evitando repetir código e nome."""
        codigo = self.codigo.strip()
        nome = (self.nome or '').strip()
        if not nome or nome == codigo:
            return codigo
        for separador in (' — ', ' - '):
            prefixo = f'{codigo}{separador}'
            if nome.startswith(prefixo):
                return nome
        return f'{codigo} — {nome}'

    def __str__(self):
        return self.rotulo


class OperadorFiltro(models.TextChoices):
    IGUAL = 'eq', 'Igual (=)'
    DIFERENTE = 'neq', 'Diferente (<>)'
    IN = 'in', 'Está em (IN)'
    NOT_IN = 'not_in', 'Não está em (NOT IN)'
    CONTEM = 'contains', 'Contém (LIKE)'
    MAIOR = 'gt', 'Maior que (>)'
    MENOR = 'lt', 'Menor que (<)'
    MAIOR_IGUAL = 'gte', 'Maior ou igual (>=)'
    MENOR_IGUAL = 'lte', 'Menor ou igual (<=)'


class FuncaoAgregacao(models.TextChoices):
    SUM = 'sum', 'Soma (SUM)'
    COUNT = 'count', 'Contagem (COUNT)'
    AVG = 'avg', 'Média (AVG)'
    MAX = 'max', 'Máximo (MAX)'
    MIN = 'min', 'Mínimo (MIN)'


class RegraMedida(models.Model):
    """
    Regra que define como calcular uma medida a partir da FatoResultadoFinanceiroQ12.

    As condições são armazenadas em JSON para flexibilidade:
    condicoes: [{"campo": "Assunto", "operador": "in", "valores": ["impostos"]}]
    joins: [{"tipo": "DimSubGrupo", "alias": "sb", "filtros": [...]}]
    group_by: ["cdEmpresa", "cdEmpreendimento", "eomonth(Data)"]
    """

    medida = models.ForeignKey(Medida, on_delete=models.CASCADE, related_name='regras')
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    ano_minimo = models.PositiveIntegerField(
        default=2024,
        help_text='Filtra YEAR(Data) >= este valor.',
    )
    funcao_agregacao = models.CharField(
        max_length=10,
        choices=FuncaoAgregacao.choices,
        default=FuncaoAgregacao.SUM,
    )
    campo_agregacao = models.CharField(
        max_length=50,
        default='valor',
        help_text='Campo numérico da fato. Ex.: valor',
    )
    condicoes = models.JSONField(
        default=list,
        blank=True,
        help_text='Filtros sobre alias f. Ex.: [{"campo":"Assunto","operador":"in","valores":["impostos"]}]',
    )
    joins = models.JSONField(
        default=list,
        blank=True,
        help_text='Joins e filtros em dimensões. Ex.: DimSubGrupo com filtros em nmSubGrupo.',
    )
    group_by = models.JSONField(
        default=list,
        blank=True,
        help_text='Campos de agrupamento. Use eomonth(Data) para competência mensal.',
    )
    sql_extra = models.TextField(
        blank=True,
        help_text='Cláusula WHERE adicional (SQL bruto). Prefixe com AND.',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['medida__ordem', 'nome']
        verbose_name = 'Regra de Medida'
        verbose_name_plural = 'Regras de Medida'

    def __str__(self):
        return f'{self.medida.codigo} — {self.nome}'

    @property
    def resumo_filtros(self) -> str:
        from controladoria.services.regra_form_utils import resumo_regra
        return resumo_regra(self)

    def clean(self):
        if not self.group_by:
            raise ValidationError({'group_by': 'Informe ao menos um campo de agrupamento.'})


class TipoExcecao(models.TextChoices):
    EXCLUIR = 'excluir', 'Excluir da regra'
    INCLUIR = 'incluir', 'Forçar inclusão na regra'


class ExcecaoLancamento(models.Model):
    """
    Lançamento específico que deve ser incluído ou excluído de uma regra,
    mesmo quando os filtros gerais dizem o contrário.
    """

    regra = models.ForeignKey(
        RegraMedida,
        on_delete=models.CASCADE,
        related_name='excecoes',
    )
    tipo = models.CharField(max_length=10, choices=TipoExcecao.choices, default=TipoExcecao.EXCLUIR)
    chave_orc = models.TextField(
        blank=True,
        help_text='ChaveOrc do lançamento na fato (identificador preferencial).',
    )
    cd_empresa = models.CharField(max_length=10, blank=True)
    cd_empreendimento = models.CharField(max_length=11, blank=True)
    cd_nucleo = models.CharField(max_length=3, blank=True)
    cd_centro = models.CharField(max_length=15, blank=True)
    data = models.DateField(null=True, blank=True, help_text='Data original do lançamento.')
    assunto = models.CharField(max_length=150, blank=True)
    classificacao = models.CharField(max_length=150, blank=True)
    cliente_fornecedor = models.CharField(max_length=150, blank=True)
    valor = models.FloatField(null=True, blank=True)
    motivo = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Exceção de Lançamento'
        verbose_name_plural = 'Exceções de Lançamento'

    def __str__(self):
        ref = self.chave_orc or f'{self.cd_empresa}/{self.cd_empreendimento}'
        return f'{self.get_tipo_display()} — {ref}'


class TipoAjuste(models.TextChoices):
    INCLUSAO = 'inclusao', 'Inclusão manual'
    EXCLUSAO = 'exclusao', 'Exclusão manual'
    RECLASSIFICACAO = 'reclassificacao', 'Reclassificar competência'


class AjusteManual(models.Model):
    """
    Ajuste manual para o BI:
    - Inclusão com data futura ou valor avulso
    - Exclusão de valor já contabilizado
    - Reclassificação de competência (mover para outro mês)
    """

    medida = models.ForeignKey(Medida, on_delete=models.CASCADE, related_name='ajustes')
    tipo = models.CharField(max_length=20, choices=TipoAjuste.choices)
    cd_empresa = models.CharField(max_length=10)
    cd_empreendimento = models.CharField(max_length=11, blank=True)
    cd_nucleo = models.CharField(max_length=3, blank=True)
    cd_centro = models.CharField(max_length=15, blank=True)
    data_competencia = models.DateField(
        help_text='Mês de competência no BI (será convertido para EOMONTH).',
    )
    data_lancamento = models.DateField(
        null=True,
        blank=True,
        help_text='Data original ou futura do lançamento (opcional).',
    )
    data_original = models.DateField(
        null=True,
        blank=True,
        help_text='Data do lançamento excluído antes do ajuste.',
    )
    valor = models.FloatField(help_text='Valor positivo ou negativo conforme o ajuste.')
    valor_original = models.FloatField(
        null=True,
        blank=True,
        help_text='Valor do lançamento excluído antes do ajuste.',
    )
    chave_orc = models.TextField(blank=True, help_text='Referência ao lançamento original, se houver.')
    observacao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_competencia', 'medida__ordem']
        verbose_name = 'Ajuste Manual'
        verbose_name_plural = 'Ajustes Manuais'

    def __str__(self):
        return f'{self.medida.codigo} — {self.data_competencia} — {self.valor}'


class TipoCompetencia(models.Model):
    """Tipo de competência (cadastro exclusivo do admin)."""

    nome = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Tipo de Competência'
        verbose_name_plural = 'Tipos de Competência'

    def __str__(self):
        return self.nome


class Competencia(models.Model):
    """Período de competência para controle de datas no sistema."""

    tipo = models.ForeignKey(
        TipoCompetencia,
        on_delete=models.PROTECT,
        related_name='competencias',
    )
    data_inicio = models.DateField()
    data_fim = models.DateField()
    competencia = models.DateField(
        help_text='Data de referência da competência (ex.: último dia do mês).',
    )

    class Meta:
        ordering = ['-competencia', 'tipo__nome']
        verbose_name = 'Competência'
        verbose_name_plural = 'Competências'

    def __str__(self):
        return f'{self.tipo} — {self.competencia:%m/%Y}'

    def clean(self):
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError({'data_fim': 'A data fim deve ser igual ou posterior à data início.'})


class TipoContaFinanceira(models.TextChoices):
    CREDITO = 'credito', 'Crédito'
    DEBITO = 'debito', 'Débito'


class ContaFinanceira(models.Model):
    """Cadastro de tipo de conta financeira (crédito ou débito)."""

    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TipoContaFinanceira.choices)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Conta Financeira'
        verbose_name_plural = 'Contas Financeiras'

    def __str__(self):
        return f'{self.nome} ({self.get_tipo_display()})'


class LancamentoFinanceiro(models.Model):
    """Lançamento financeiro vinculado a empreendimento, sócio e conta."""

    conta = models.ForeignKey(
        ContaFinanceira,
        on_delete=models.PROTECT,
        related_name='lancamentos',
    )
    empreendimento = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name='lancamentos_financeiros',
        verbose_name='Empreendimento',
    )
    socio = models.ForeignKey(
        Socio,
        on_delete=models.PROTECT,
        related_name='lancamentos_financeiros',
    )
    data_competencia = models.DateField(
        help_text='Data de competência do lançamento.',
    )
    valor = models.DecimalField(max_digits=18, decimal_places=2)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_competencia', '-criado_em']
        verbose_name = 'Lançamento Financeiro'
        verbose_name_plural = 'Lançamentos Financeiros'

    def __str__(self):
        return (
            f'{self.conta} — {self.empreendimento} — '
            f'{self.data_competencia:%d/%m/%Y} — {self.valor}'
        )

    def clean(self):
        if self.valor is not None and self.valor == 0:
            raise ValidationError({'valor': 'Informe um valor diferente de zero.'})


class ImovelVendido(models.Model):
    """Imóvel vendido importado da planilha padrão de comissão (aba Resumo)."""

    empreendimento_ajustado = models.CharField(max_length=150, blank=True)
    cod_empreendimento = models.CharField(max_length=20, blank=True)
    data_venda = models.DateField(null=True, blank=True)
    contrato_ajustado = models.CharField(max_length=40, unique=True)
    situacao = models.CharField(max_length=40, blank=True)
    imovel = models.CharField(max_length=200, blank=True)
    cliente = models.CharField(max_length=200, blank=True)
    valor_tabela = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    desconto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_venda = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_liquidado = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    situacao_contrato = models.CharField(max_length=40, blank=True)
    data_rescisao_imobiliaria = models.DateField(null=True, blank=True)
    imobiliaria = models.CharField(max_length=150, blank=True)
    corretor = models.CharField(max_length=150, blank=True)
    regra_comissao = models.CharField(max_length=40, blank=True)
    comissao = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    regra_valor = models.CharField(max_length=10, blank=True)
    competencia = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_venda', 'contrato_ajustado']
        verbose_name = 'Imóvel Vendido'
        verbose_name_plural = 'Imóveis Vendidos'

    def __str__(self):
        return f'{self.contrato_ajustado} — {self.cliente or self.imovel or "sem cliente"}'


class Comissao(models.Model):
    """Comissão de parceria incluída para pagamento."""

    cd_contrato = models.CharField(max_length=16, unique=True)
    data_contrato = models.DateField(null=True, blank=True)
    cd_empresa = models.CharField(max_length=3)
    contrato = models.CharField(max_length=6, blank=True)
    situacao = models.CharField(max_length=1, blank=True)
    cd_cliente = models.CharField(max_length=4, blank=True)
    cliente = models.CharField(max_length=50, blank=True)
    valor_tabela_primeira = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_tabela_venda = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_venda_a_vista = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    desconto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    liquidado = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    percentual = models.FloatField(null=True, blank=True)
    comissao = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    data_corte = models.DateField(help_text='Data de corte usada na consulta de pagamentos.')
    mes_fechamento = models.PositiveSmallIntegerField(null=True, blank=True)
    ano_fechamento = models.PositiveSmallIntegerField(null=True, blank=True)
    data_pagamento = models.DateField(help_text='Data prevista para pagamento da comissão.')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comissoes_criadas',
    )

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Comissão'
        verbose_name_plural = 'Comissões'

    def __str__(self):
        return f'{self.cd_contrato} — {self.data_pagamento:%d/%m/%Y}'
