from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory
from django.forms.models import InlineForeignKeyField, construct_instance

from controladoria.models import (
    AjusteManual,
    Competencia,
    ContaFinanceira,
    Empresa,
    ExcecaoLancamento,
    FuncaoAgregacao,
    ImovelVendido,
    LancamentoFinanceiro,
    Medida,
    OperadorFiltro,
    RegraMedida,
    SegmentoEmpresa,
    Socio,
    SocioEmpresa,
    TipoCompetencia,
    TipoContaFinanceira,
    TipoAjuste,
    TipoExcecao,
)
from controladoria.services.ajustes import (
    dados_lancamento_from_request,
    row_referencia_from_ajuste,
    soma_ajustes_lancamento,
    validar_soma_ajustes,
)
from controladoria.services.motor_regras import MotorRegrasError
from controladoria.services.consulta_base import campos_agregacao
from controladoria.services.regra_form_utils import (
    AGRUPAMENTO_OPCOES,
    OPERADOR_RAIZ_CHOICES,
    agrupamentos_from_group_by,
    condicoes_from_post,
    condicoes_tem_itens,
    filtros_padrao,
    group_by_from_form,
    joins_from_condicoes,
    normalizar_condicoes,
)


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['empresa', 'nome', 'segmento', 'percentual_venda']
        widgets = {
            'empresa': forms.TextInput(attrs={
                'placeholder': 'Ex.: 001',
                'maxlength': '3',
            }),
            'nome': forms.TextInput(attrs={'placeholder': 'Nome da empresa'}),
            'segmento': forms.Select(choices=SegmentoEmpresa.choices),
            'percentual_venda': forms.NumberInput(attrs={
                'placeholder': 'Ex.: 85,50',
                'step': '0.01',
                'min': '0',
                'max': '100',
            }),
        }
        labels = {
            'empresa': 'Código',
            'nome': 'Nome',
            'segmento': 'Segmento',
            'percentual_venda': 'Percentual de venda',
        }
        help_texts = {
            'empresa': 'Código único da empresa (até 3 caracteres).',
            'percentual_venda': 'Informe um valor entre 0 e 100.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')

    def clean_empresa(self):
        codigo = (self.cleaned_data.get('empresa') or '').strip().upper()
        if not codigo:
            raise ValidationError('Informe o código da empresa.')
        if len(codigo) > 3:
            raise ValidationError('O código deve ter no máximo 3 caracteres.')

        duplicada = Empresa.objects.filter(empresa__iexact=codigo)
        if self.instance.pk:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise ValidationError('Já existe uma empresa cadastrada com este código.')

        return codigo

    def clean_percentual_venda(self):
        valor = self.cleaned_data.get('percentual_venda')
        if valor is None:
            return valor
        if valor < 0 or valor > 100:
            raise ValidationError('O percentual de venda deve estar entre 0 e 100.')
        return valor


class SocioForm(forms.ModelForm):
    class Meta:
        model = Socio
        fields = ['nome', 'documento', 'email', 'telefone', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Nome completo'}),
            'documento': forms.TextInput(attrs={'placeholder': 'CPF ou CNPJ'}),
            'email': forms.EmailInput(attrs={'placeholder': 'email@exemplo.com'}),
            'telefone': forms.TextInput(attrs={'placeholder': '(00) 00000-0000'}),
        }
        labels = {
            'nome': 'Nome',
            'documento': 'Documento',
            'email': 'E-mail',
            'telefone': 'Telefone',
            'ativo': 'Ativo',
        }
        help_texts = {
            'documento': 'CPF ou CNPJ (opcional).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'ativo':
                continue
            field.widget.attrs.setdefault('class', 'input')

    def clean_nome(self):
        nome = (self.cleaned_data.get('nome') or '').strip()
        if not nome:
            raise ValidationError('Informe o nome do sócio.')
        return nome

    def clean_documento(self):
        documento = (self.cleaned_data.get('documento') or '').strip()
        if not documento:
            return ''
        duplicado = Socio.objects.filter(documento__iexact=documento)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise ValidationError('Já existe um sócio cadastrado com este documento.')
        return documento


class SocioEmpresaForm(forms.ModelForm):
    class Meta:
        model = SocioEmpresa
        fields = ['empresa', 'percentual', 'taxa_administracao']
        widgets = {
            'empresa': forms.Select(),
            'percentual': forms.NumberInput(attrs={
                'placeholder': 'Ex.: 50,00',
                'step': '0.01',
                'min': '0',
                'max': '100',
            }),
            'taxa_administracao': forms.NumberInput(attrs={
                'placeholder': 'Ex.: 2,50',
                'step': '0.01',
                'min': '0',
                'max': '100',
            }),
        }
        labels = {
            'empresa': 'Empresa',
            'percentual': '% Participação',
            'taxa_administracao': 'Taxa adm. (%)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].queryset = Empresa.objects.order_by('empresa')
        self.fields['empresa'].empty_label = 'Selecione a empresa'
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')

    def clean_percentual(self):
        valor = self.cleaned_data.get('percentual')
        if valor is not None and (valor < 0 or valor > 100):
            raise ValidationError('O percentual deve estar entre 0 e 100.')
        return valor

    def clean_taxa_administracao(self):
        valor = self.cleaned_data.get('taxa_administracao')
        if valor is not None and (valor < 0 or valor > 100):
            raise ValidationError('A taxa de administração deve estar entre 0 e 100.')
        return valor


SocioEmpresaFormSetBase = inlineformset_factory(
    Socio,
    SocioEmpresa,
    form=SocioEmpresaForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class SocioEmpresaFormSet(SocioEmpresaFormSetBase):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        empresas = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            empresa = form.cleaned_data.get('empresa')
            if not empresa:
                continue
            if empresa.pk in empresas:
                raise ValidationError('Não é permitido relacionar a mesma empresa mais de uma vez ao sócio.')
            empresas.append(empresa.pk)


class CompetenciaForm(forms.ModelForm):
    class Meta:
        model = Competencia
        fields = ['tipo', 'data_inicio', 'data_fim', 'competencia']
        widgets = {
            'tipo': forms.Select(),
            'data_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'data_fim': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'competencia': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }
        labels = {
            'tipo': 'Tipo',
            'data_inicio': 'Data início',
            'data_fim': 'Data fim',
            'competencia': 'Competência',
        }
        help_texts = {
            'competencia': 'Data de referência da competência (ex.: último dia do mês).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].queryset = TipoCompetencia.objects.order_by('nome')
        self.fields['tipo'].empty_label = 'Selecione o tipo'
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')
        for name in ('data_inicio', 'data_fim', 'competencia'):
            self.fields[name].input_formats = ['%Y-%m-%d']

    def clean(self):
        cleaned = super().clean()
        data_inicio = cleaned.get('data_inicio')
        data_fim = cleaned.get('data_fim')
        if data_inicio and data_fim and data_fim < data_inicio:
            raise ValidationError({'data_fim': 'A data fim deve ser igual ou posterior à data início.'})
        return cleaned


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = ['nome', 'tipo', 'descricao', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex.: Distribuição de lucros'}),
            'tipo': forms.Select(choices=TipoContaFinanceira.choices),
            'descricao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Descrição opcional'}),
        }
        labels = {
            'nome': 'Nome',
            'tipo': 'Tipo',
            'descricao': 'Descrição',
            'ativo': 'Ativo',
        }
        help_texts = {
            'tipo': 'Informe se a conta é de crédito ou débito.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'ativo':
                continue
            field.widget.attrs.setdefault('class', 'input')

    def clean_nome(self):
        nome = (self.cleaned_data.get('nome') or '').strip()
        if not nome:
            raise ValidationError('Informe o nome da conta.')
        duplicada = ContaFinanceira.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise ValidationError('Já existe uma conta financeira com este nome.')
        return nome


class LancamentoFinanceiroForm(forms.ModelForm):
    class Meta:
        model = LancamentoFinanceiro
        fields = [
            'conta',
            'empreendimento',
            'socio',
            'data_competencia',
            'valor',
            'observacao',
        ]
        widgets = {
            'conta': forms.Select(),
            'empreendimento': forms.Select(),
            'socio': forms.Select(),
            'data_competencia': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'valor': forms.NumberInput(attrs={
                'placeholder': 'Ex.: 1500,00',
                'step': '0.01',
            }),
            'observacao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Observação opcional'}),
        }
        labels = {
            'conta': 'Conta financeira',
            'empreendimento': 'Empreendimento',
            'socio': 'Sócio',
            'data_competencia': 'Data competência',
            'valor': 'Valor',
            'observacao': 'Observação',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contas = ContaFinanceira.objects.filter(ativo=True).order_by('nome')
        if self.instance.pk and self.instance.conta_id:
            contas = ContaFinanceira.objects.filter(
                Q(ativo=True) | Q(pk=self.instance.conta_id)
            ).order_by('nome')
        self.fields['conta'].queryset = contas
        self.fields['conta'].empty_label = 'Selecione a conta'
        self.fields['empreendimento'].queryset = Empresa.objects.order_by('empresa')
        self.fields['empreendimento'].empty_label = 'Selecione o empreendimento'
        socios = Socio.objects.filter(ativo=True).order_by('nome')
        if self.instance.pk and self.instance.socio_id:
            socios = Socio.objects.filter(
                Q(ativo=True) | Q(pk=self.instance.socio_id)
            ).order_by('nome')
        self.fields['socio'].queryset = socios
        self.fields['socio'].empty_label = 'Selecione o sócio'
        self.fields['data_competencia'].input_formats = ['%Y-%m-%d']
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        if valor is None:
            raise ValidationError('Informe o valor do lançamento.')
        if valor == 0:
            raise ValidationError('Informe um valor diferente de zero.')
        return valor


class ImovelVendidoForm(forms.ModelForm):
    class Meta:
        model = ImovelVendido
        fields = [
            'empreendimento_ajustado',
            'cod_empreendimento',
            'data_venda',
            'contrato_ajustado',
            'situacao',
            'imovel',
            'cliente',
            'valor_tabela',
            'desconto',
            'valor_venda',
            'valor_liquidado',
            'situacao_contrato',
            'data_rescisao_imobiliaria',
            'imobiliaria',
            'corretor',
            'regra_comissao',
            'comissao',
            'regra_valor',
            'competencia',
        ]
        widgets = {
            'empreendimento_ajustado': forms.TextInput(attrs={'placeholder': 'Empreendimento ajustado'}),
            'cod_empreendimento': forms.TextInput(attrs={'placeholder': 'Ex.: CPA'}),
            'data_venda': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'contrato_ajustado': forms.TextInput(attrs={'placeholder': 'Ex.: CPA0176-0'}),
            'situacao': forms.TextInput(attrs={'placeholder': 'Ativo, Rescindido...'}),
            'imovel': forms.TextInput(attrs={'placeholder': 'Identificação do imóvel'}),
            'cliente': forms.TextInput(attrs={'placeholder': 'Nome do cliente'}),
            'valor_tabela': forms.NumberInput(attrs={'step': '0.01'}),
            'desconto': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_venda': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_liquidado': forms.NumberInput(attrs={'step': '0.01'}),
            'situacao_contrato': forms.TextInput(),
            'data_rescisao_imobiliaria': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'imobiliaria': forms.TextInput(),
            'corretor': forms.TextInput(),
            'regra_comissao': forms.TextInput(attrs={'placeholder': 'Considerar / Desconsiderar'}),
            'comissao': forms.NumberInput(attrs={'step': '0.01'}),
            'regra_valor': forms.TextInput(attrs={'placeholder': 'Sim / Não'}),
            'competencia': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }
        labels = {
            'empreendimento_ajustado': 'Empreendimento ajustado',
            'cod_empreendimento': 'Cód. empreendimento',
            'data_venda': 'Data da venda',
            'contrato_ajustado': 'Contrato ajustado',
            'situacao': 'Situação',
            'imovel': 'Imóvel',
            'cliente': 'Cliente',
            'valor_tabela': 'Valor tabela',
            'desconto': 'Desconto',
            'valor_venda': 'Valor venda',
            'valor_liquidado': 'Valor liquidado',
            'situacao_contrato': 'Situação do contrato',
            'data_rescisao_imobiliaria': 'Data de rescisão imobiliária',
            'imobiliaria': 'Imobiliária',
            'corretor': 'Corretor',
            'regra_comissao': 'Regra comissão',
            'comissao': 'Comissão',
            'regra_valor': 'Regra valor',
            'competencia': 'Competência',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('data_venda', 'data_rescisao_imobiliaria', 'competencia'):
            self.fields[name].input_formats = ['%Y-%m-%d']
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')

    def clean_contrato_ajustado(self):
        contrato = (self.cleaned_data.get('contrato_ajustado') or '').strip()
        if not contrato:
            raise ValidationError('Informe o contrato ajustado.')
        duplicado = ImovelVendido.objects.filter(contrato_ajustado__iexact=contrato)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise ValidationError('Já existe um imóvel vendido com este contrato ajustado.')
        return contrato


class ImovelVendidoImportForm(forms.Form):
    arquivo = forms.FileField(
        label='Planilha Excel',
        help_text='Arquivo .xlsx com a aba Resumo (planilha padrão de comissão).',
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'class': 'input',
        }),
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if not arquivo:
            raise ValidationError('Selecione um arquivo para importar.')
        nome = (arquivo.name or '').lower()
        if not nome.endswith('.xlsx'):
            raise ValidationError('Envie um arquivo Excel no formato .xlsx.')
        return arquivo


class MedidaForm(forms.ModelForm):
    class Meta:
        model = Medida
        fields = ['codigo', 'nome', 'descricao', 'ordem', 'ativo']
        widgets = {
            'codigo': forms.TextInput(attrs={'placeholder': 'Ex.: ImpostoISS_IPTU'}),
            'nome': forms.TextInput(attrs={'placeholder': 'Nome de exibição'}),
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault('class', 'input')


class RegraMedidaForm(forms.ModelForm):
    """Formulário visual — gera JSON internamente ao salvar."""

    agrupamentos = forms.MultipleChoiceField(
        required=True,
        label='Agrupar resultado por',
        choices=AGRUPAMENTO_OPCOES,
        widget=forms.CheckboxSelectMultiple,
        help_text='Marque as colunas que devem aparecer no BI.',
    )

    class Meta:
        model = RegraMedida
        fields = [
            'medida', 'nome', 'descricao', 'ativo', 'ano_minimo',
            'funcao_agregacao', 'campo_agregacao', 'sql_extra',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex.: ISS e IPTU — débito'}),
            'descricao': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Descrição opcional'}),
            'ano_minimo': forms.NumberInput(attrs={'min': 2000, 'max': 2100}),
            'sql_extra': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Somente para casos especiais (SQL adicional)',
            }),
        }
        labels = {
            'medida': 'Medida',
            'ano_minimo': 'Ano mínimo dos lançamentos',
            'funcao_agregacao': 'Como calcular',
            'campo_agregacao': 'Campo numérico',
            'sql_extra': 'Filtro avançado (opcional)',
        }

    def __init__(self, *args, **kwargs):
        self._condicoes_post = kwargs.pop('condicoes_post', None)
        super().__init__(*args, **kwargs)
        self.fields['campo_agregacao'].widget = forms.Select(choices=campos_agregacao())
        self.fields['funcao_agregacao'].label = 'Como calcular'

        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            field.widget.attrs.setdefault('class', 'input')

        if self.instance.pk:
            self.fields['agrupamentos'].initial = agrupamentos_from_group_by(self.instance.group_by)
        else:
            self.fields['agrupamentos'].initial = ['cdEmpresa', 'cdEmpreendimento', 'mes']

    def aplicar_condicoes_post(self, post_data):
        self._condicoes_post = condicoes_from_post(post_data)

    def clean(self):
        cleaned = super().clean()
        condicoes = self._condicoes_post if self._condicoes_post is not None else {}
        if not condicoes_tem_itens(condicoes):
            raise ValidationError('Adicione ao menos um filtro na seção "Quando buscar lançamentos".')

        agrupamentos = cleaned.get('agrupamentos') or []
        if not agrupamentos:
            self.add_error('agrupamentos', 'Marque ao menos uma opção de agrupamento.')

        return cleaned

    def _aplicar_campos_json(self):
        """Mapeia campos visuais do form para JSON do model antes da validação."""
        condicoes = self._condicoes_post or filtros_padrao()
        self.instance.condicoes = condicoes
        self.instance.joins = joins_from_condicoes(condicoes)
        self.instance.group_by = group_by_from_form(self.cleaned_data.get('agrupamentos', []))

    def _update_errors(self, errors):
        if hasattr(errors, 'error_dict') and 'group_by' in errors.error_dict:
            errors.error_dict['agrupamentos'] = errors.error_dict.pop('group_by')
        super()._update_errors(errors)

    def _post_clean(self):
        opts = self._meta
        exclude = self._get_validation_exclusions()

        for name, field in self.fields.items():
            if isinstance(field, InlineForeignKeyField):
                exclude.add(name)

        try:
            self.instance = construct_instance(
                self, self.instance, opts.fields, opts.exclude,
            )
        except ValidationError as e:
            self._update_errors(e)
            return

        self._aplicar_campos_json()

        try:
            self.instance.full_clean(
                exclude=exclude,
                validate_unique=False,
                validate_constraints=False,
            )
        except ValidationError as e:
            self._update_errors(e)

    def save(self, commit=True):
        self._aplicar_campos_json()
        return super().save(commit=commit)

    def get_filtros_grupos(self):
        if self._condicoes_post is not None:
            return normalizar_condicoes(self._condicoes_post)
        if self.instance.pk and self.instance.condicoes:
            return normalizar_condicoes(self.instance.condicoes, self.instance.joins)
        return filtros_padrao()


class ExcecaoLancamentoForm(forms.ModelForm):
    class Meta:
        model = ExcecaoLancamento
        fields = [
            'regra', 'tipo', 'chave_orc', 'cd_empresa', 'cd_empreendimento',
            'cd_nucleo', 'cd_centro', 'data', 'assunto', 'classificacao',
            'cliente_fornecedor', 'valor', 'motivo', 'ativo',
        ]
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}),
            'motivo': forms.Textarea(attrs={'rows': 3}),
            'chave_orc': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault('class', 'input')


class AjusteGerarLancamentoForm(forms.Form):
    data_competencia = forms.DateField(
        label='Nova data',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    valor = forms.FloatField(
        label='Novo valor',
        widget=forms.NumberInput(attrs={'step': '0.01'}),
    )
    observacao = forms.CharField(
        required=False,
        label='Observação',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Opcional'}),
    )
    data_original = forms.DateField(widget=forms.HiddenInput)
    valor_original = forms.FloatField(widget=forms.HiddenInput)
    regra_id = forms.IntegerField(widget=forms.HiddenInput)
    medida_id = forms.IntegerField(widget=forms.HiddenInput)
    chave_orc = forms.CharField(required=False, widget=forms.HiddenInput)
    cd_empresa = forms.CharField(widget=forms.HiddenInput)
    cd_empreendimento = forms.CharField(required=False, widget=forms.HiddenInput)
    cd_nucleo = forms.CharField(required=False, widget=forms.HiddenInput)
    cd_centro = forms.CharField(required=False, widget=forms.HiddenInput)
    assunto = forms.CharField(required=False, widget=forms.HiddenInput)
    classificacao = forms.CharField(required=False, widget=forms.HiddenInput)
    cliente_fornecedor = forms.CharField(required=False, widget=forms.HiddenInput)
    q_retorno = forms.CharField(required=False, widget=forms.HiddenInput)
    page_retorno = forms.CharField(required=False, widget=forms.HiddenInput)
    data_inicio_retorno = forms.CharField(required=False, widget=forms.HiddenInput)
    data_fim_retorno = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        self._resumo_ajustes = kwargs.pop('resumo_ajustes', None)
        super().__init__(*args, **kwargs)
        self.fields['data_competencia'].input_formats = ['%Y-%m-%d']
        for name in ('data_competencia', 'valor', 'observacao', 'data_original'):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault('class', 'input')
        if self._resumo_ajustes and self._resumo_ajustes.get('valor_restante') is not None:
            restante = self._resumo_ajustes['valor_restante']
            self.fields['valor'].help_text = (
                f"Valor restante disponível para ajustes: R$ {restante:,.2f}"
                .replace(',', 'X').replace('.', ',').replace('X', '.')
            )

    def clean(self):
        cleaned = super().clean()
        medida_id = cleaned.get('medida_id')
        valor = cleaned.get('valor')
        if medida_id is None or valor is None:
            return cleaned

        try:
            medida = Medida.objects.get(pk=medida_id)
        except Medida.DoesNotExist:
            return cleaned

        row = dados_lancamento_from_request(cleaned)
        valor_original = cleaned.get('valor_original')
        soma_atual = soma_ajustes_lancamento(medida, row)
        try:
            validar_soma_ajustes(valor_original, soma_atual, valor)
        except MotorRegrasError as exc:
            self.add_error('valor', str(exc))
        return cleaned


class AjusteEditForm(forms.ModelForm):
    """Edição restrita: apenas nova data e novo valor."""

    class Meta:
        model = AjusteManual
        fields = ['data_competencia', 'valor']
        labels = {
            'data_competencia': 'Nova data',
            'valor': 'Novo valor',
        }
        widgets = {
            'data_competencia': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'},
            ),
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_competencia'].input_formats = ['%Y-%m-%d']
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')
        if self.instance.pk and self.instance.valor_original is not None:
            row = row_referencia_from_ajuste(self.instance)
            soma = soma_ajustes_lancamento(
                self.instance.medida,
                row,
                excluir_id=self.instance.pk,
            )
            restante = float(self.instance.valor_original) - soma
            self.fields['valor'].help_text = (
                f"Valor restante disponível (sem contar este ajuste): "
                f"R$ {restante:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            )

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            return cleaned

        valor = cleaned.get('valor')
        if valor is None:
            return cleaned

        row = row_referencia_from_ajuste(self.instance)
        soma = soma_ajustes_lancamento(
            self.instance.medida,
            row,
            excluir_id=self.instance.pk,
        )
        try:
            validar_soma_ajustes(self.instance.valor_original, soma, valor)
        except MotorRegrasError as exc:
            self.add_error('valor', str(exc))
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.data_lancamento = obj.data_competencia
        if commit:
            obj.save()
        return obj


class AjusteManualForm(forms.ModelForm):
    class Meta:
        model = AjusteManual
        fields = [
            'medida', 'cd_empresa', 'cd_empreendimento', 'cd_nucleo',
            'cd_centro', 'data_competencia', 'valor',
            'chave_orc', 'observacao', 'ativo',
        ]
        widgets = {
            'data_competencia': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'},
            ),
            'observacao': forms.Textarea(attrs={'rows': 3}),
            'chave_orc': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'data_competencia': 'Nova data',
            'valor': 'Novo valor',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_competencia'].input_formats = ['%Y-%m-%d']
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault('class', 'input')

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.data_lancamento = obj.data_competencia
        if not obj.tipo:
            obj.tipo = TipoAjuste.RECLASSIFICACAO
        if commit:
            obj.save()
        return obj
