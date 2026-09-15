from django.contrib import admin, messages
from django.utils.html import format_html

from controladoria.models import (
    AjusteManual,
    Comissao,
    Competencia,
    ContaFinanceira,
    Empresa,
    ExcecaoLancamento,
    ImovelVendido,
    LancamentoFinanceiro,
    Medida,
    RegraMedida,
    Socio,
    SocioEmpresa,
    TipoCompetencia,
)
from controladoria.services.empresa_dw import EmpresaDWError, remover_empresa_dw, sincronizar_empresa_dw
from controladoria.services.motor_regras import gerar_sql_regra


class RegraMedidaInline(admin.TabularInline):
    model = RegraMedida
    extra = 0
    fields = ('nome', 'ativo', 'ano_minimo', 'funcao_agregacao')


class ExcecaoLancamentoInline(admin.TabularInline):
    model = ExcecaoLancamento
    extra = 0
    fields = ('tipo', 'chave_orc', 'cd_empresa', 'valor', 'motivo', 'ativo')


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'nome', 'segmento', 'percentual_venda')
    list_filter = ('segmento',)
    search_fields = ('empresa', 'nome')

    def save_model(self, request, obj, form, change):
        codigo_anterior = None
        if change and obj.pk:
            codigo_anterior = Empresa.objects.filter(pk=obj.pk).values_list('empresa', flat=True).first()

        super().save_model(request, obj, form, change)

        try:
            sincronizar_empresa_dw(obj)
            if codigo_anterior and codigo_anterior.upper() != obj.empresa.upper():
                remover_empresa_dw(codigo_anterior)
        except EmpresaDWError as err:
            self.message_user(request, str(err), level=messages.ERROR)

    def delete_model(self, request, obj):
        try:
            remover_empresa_dw(obj)
        except EmpresaDWError as err:
            self.message_user(request, str(err), level=messages.ERROR)
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


class SocioEmpresaInline(admin.TabularInline):
    model = SocioEmpresa
    extra = 1
    autocomplete_fields = ('empresa',)


@admin.register(Socio)
class SocioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'documento', 'email', 'telefone', 'ativo', 'atualizado_em')
    list_filter = ('ativo',)
    search_fields = ('nome', 'documento', 'email')
    inlines = [SocioEmpresaInline]


@admin.register(SocioEmpresa)
class SocioEmpresaAdmin(admin.ModelAdmin):
    list_display = ('socio', 'empresa', 'percentual', 'taxa_administracao')
    list_filter = ('empresa',)
    search_fields = ('socio__nome', 'empresa__empresa', 'empresa__nome')
    autocomplete_fields = ('socio', 'empresa')


@admin.register(Medida)
class MedidaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'ordem', 'ativo', 'atualizado_em')
    list_filter = ('ativo',)
    search_fields = ('codigo', 'nome')
    ordering = ('ordem', 'codigo')
    inlines = [RegraMedidaInline]


@admin.register(RegraMedida)
class RegraMedidaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'medida', 'ativo', 'ano_minimo', 'funcao_agregacao', 'link_preview', 'atualizado_em')
    list_filter = ('ativo', 'medida', 'funcao_agregacao')
    search_fields = ('nome', 'medida__codigo')
    readonly_fields = ('sql_preview', 'link_preview', 'criado_em', 'atualizado_em')
    inlines = [ExcecaoLancamentoInline]
    fieldsets = (
        (None, {
            'fields': ('medida', 'nome', 'descricao', 'ativo'),
        }),
        ('Agregação', {
            'fields': ('funcao_agregacao', 'campo_agregacao', 'ano_minimo', 'group_by'),
        }),
        ('Filtros (JSON)', {
            'fields': ('condicoes', 'joins', 'sql_extra'),
            'description': (
                'Exemplo condicoes: [{"campo":"Assunto","operador":"in","valores":["impostos"]}, '
                '{"campo":"DC","operador":"eq","valores":["D"]}]'
            ),
        }),
        ('SQL gerado', {
            'fields': ('sql_preview', 'link_preview'),
        }),
        ('Auditoria', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Preview')
    def link_preview(self, obj):
        if not obj.pk:
            return '-'
        from django.urls import reverse
        url = reverse('controladoria:regra_preview', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Executar</a>', url)

    @admin.display(description='SQL gerado')
    def sql_preview(self, obj):
        if not obj.pk:
            return 'Salve a regra para visualizar o SQL.'
        try:
            sql = gerar_sql_regra(obj)
        except Exception as exc:
            return str(exc)
        return format_html('<pre style="white-space:pre-wrap">{}</pre>', sql)


@admin.register(ExcecaoLancamento)
class ExcecaoLancamentoAdmin(admin.ModelAdmin):
    list_display = ('regra', 'tipo', 'chave_orc', 'cd_empresa', 'valor', 'ativo', 'criado_em')
    list_filter = ('tipo', 'ativo', 'regra__medida')
    search_fields = ('chave_orc', 'cd_empresa', 'motivo')


@admin.register(TipoCompetencia)
class TipoCompetenciaAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)
    ordering = ('nome',)


@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'competencia', 'data_inicio', 'data_fim')
    list_filter = ('tipo',)
    search_fields = ('tipo__nome',)
    date_hierarchy = 'competencia'
    ordering = ('-competencia', 'tipo__nome')


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'ativo', 'atualizado_em')
    list_filter = ('tipo', 'ativo')
    search_fields = ('nome', 'descricao')


@admin.register(LancamentoFinanceiro)
class LancamentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = (
        'data_competencia', 'conta', 'empreendimento', 'socio', 'valor', 'atualizado_em',
    )
    list_filter = ('conta__tipo', 'conta', 'empreendimento')
    search_fields = (
        'observacao',
        'socio__nome',
        'empreendimento__empresa',
        'empreendimento__nome',
        'conta__nome',
    )
    autocomplete_fields = ('conta', 'empreendimento', 'socio')
    date_hierarchy = 'data_competencia'


@admin.register(ImovelVendido)
class ImovelVendidoAdmin(admin.ModelAdmin):
    list_display = (
        'contrato_ajustado',
        'data_venda',
        'cod_empreendimento',
        'cliente',
        'situacao',
        'valor_venda',
        'comissao',
        'competencia',
        'atualizado_em',
    )
    list_filter = ('situacao', 'regra_comissao', 'cod_empreendimento')
    search_fields = (
        'contrato_ajustado',
        'cliente',
        'imovel',
        'empreendimento_ajustado',
        'corretor',
        'imobiliaria',
    )
    date_hierarchy = 'data_venda'


@admin.register(AjusteManual)
class AjusteManualAdmin(admin.ModelAdmin):
    list_display = (
        'medida', 'tipo', 'cd_empresa', 'cd_empreendimento',
        'data_competencia', 'valor', 'ativo',
    )
    list_filter = ('tipo', 'ativo', 'medida')
    search_fields = ('cd_empresa', 'chave_orc', 'observacao')
    date_hierarchy = 'data_competencia'


@admin.register(Comissao)
class ComissaoAdmin(admin.ModelAdmin):
    list_display = (
        'cd_contrato', 'cd_empresa', 'cliente', 'comissao', 'data_pagamento', 'data_corte', 'criado_em',
    )
    list_filter = ('cd_empresa', 'data_pagamento', 'data_corte')
    search_fields = ('cd_contrato', 'cliente', 'cd_empresa')
    readonly_fields = ('criado_em', 'criado_por')
    date_hierarchy = 'criado_em'
