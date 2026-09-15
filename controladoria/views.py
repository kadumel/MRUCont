from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView, View

from controladoria.forms import (
    AjusteEditForm,
    AjusteGerarLancamentoForm,
    AjusteManualForm,
    CompetenciaForm,
    ContaFinanceiraForm,
    EmpresaForm,
    ExcecaoLancamentoForm,
    ImovelVendidoForm,
    ImovelVendidoImportForm,
    LancamentoFinanceiroForm,
    MedidaForm,
    RegraMedidaForm,
    SocioEmpresaFormSet,
    SocioForm,
)
from controladoria.mixins import ControladoriaLayoutMixin
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
    OperadorFiltro,
    RegraMedida,
    Socio,
    TipoCompetencia,
    TipoContaFinanceira,
)
from controladoria.services.ajuste_dw import AjusteDWError, atualizar_ajuste_dw, inserir_ajuste_dw
from controladoria.services.empresa_dw import EmpresaDWError, remover_empresa_dw, sincronizar_empresa_dw
from controladoria.services.ajustes import (
    buscar_lancamentos_excluidos,
    criar_ajuste_lancamento,
    dados_lancamento_from_request,
    resumo_ajustes_lancamento,
)
from controladoria.services.excecoes import (
    _parse_filtros_lancamentos,
    buscar_lancamentos_regra,
    criar_excecao_lancamento,
    excluir_excecao_lancamento,
    obter_regras_medida,
)
from controladoria.services.consulta_base import campo_na_listagem, campos_filtro
from controladoria.services.comissoes import (
    ComissaoError,
    atualizar_data_pagamento,
    buscar_comissoes_dw,
    excluir_comissao,
    incluir_comissao,
)
from controladoria.services.imoveis_vendidos import (
    ImovelVendidoImportError,
    importar_imoveis_vendidos,
)
from controladoria.services.regra_form_utils import OPERADOR_RAIZ_CHOICES, condicoes_from_post
from controladoria.services.motor_regras import (
    MotorRegrasError,
    executar_medidas,
    gerar_sql_consolidado,
    preview_regra,
    resumo_configuracao,
)
from controladoria.services.view_regras_dw import ViewRegrasDWError, atualizar_view_regras_dw


class PortalLoginView(LoginView):
    template_name = 'controladoria/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse('controladoria:medida_list')

    def form_valid(self, form):
        # Expira a sessão depois do login para não perder o cookie no cycle_key.
        response = super().form_valid(form)
        if self.request.POST.get('remember_me'):
            # 14 dias
            self.request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            # Sessão persistente do turno (evita set_expiry(0), que vira cookie
            # de browser e costuma cair no refresh em alguns ambientes).
            self.request.session.set_expiry(60 * 60 * 12)
        return response


@require_POST
def portal_logout(request):
    logout(request)
    return redirect('controladoria:login')


class DashboardView(ControladoriaLayoutMixin, TemplateView):
    template_name = 'controladoria/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'dashboard'
        ctx['resumo'] = resumo_configuracao()
        ctx['sql'] = gerar_sql_consolidado()
        ctx['resultado'] = None
        ctx['erro'] = None
        ctx['view_dw'] = None
        ctx['view_dw_erro'] = None

        if ctx['resumo']['dw_configurado']:
            try:
                ctx['view_dw'] = atualizar_view_regras_dw()
            except ViewRegrasDWError as exc:
                ctx['view_dw_erro'] = str(exc)

        if self.request.GET.get('executar') == '1':
            try:
                ctx['resultado'] = executar_medidas()
            except MotorRegrasError as exc:
                ctx['erro'] = str(exc)
        return ctx


class EmpresaListView(ControladoriaLayoutMixin, ListView):
    model = Empresa
    template_name = 'controladoria/empresa_list.html'
    context_object_name = 'empresas'
    paginate_by = 25

    def get_queryset(self):
        qs = Empresa.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(empresa__icontains=q) | Q(nome__icontains=q))
        segmento = self.request.GET.get('segmento', '').strip()
        if segmento:
            qs = qs.filter(segmento=segmento)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'empresas'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['segmento'] = self.request.GET.get('segmento', '')
        return ctx


class EmpresaCreateView(ControladoriaLayoutMixin, CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'controladoria/empresa_form.html'
    success_url = reverse_lazy('controladoria:empresa_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'empresas'
        ctx['page_title'] = 'Nova empresa'
        return ctx

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save()
                sincronizar_empresa_dw(self.object)
        except EmpresaDWError as err:
            form.add_error(None, str(err))
            return self.form_invalid(form)
        messages.success(self.request, 'Empresa cadastrada com sucesso.')
        return redirect(self.get_success_url())


class EmpresaUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'controladoria/empresa_form.html'
    success_url = reverse_lazy('controladoria:empresa_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'empresas'
        ctx['page_title'] = f'Editar — {self.object.empresa}'
        return ctx

    def form_valid(self, form):
        codigo_anterior = None
        if self.object.pk:
            codigo_anterior = (
                Empresa.objects.filter(pk=self.object.pk)
                .values_list('empresa', flat=True)
                .first()
            )
        try:
            with transaction.atomic():
                self.object = form.save()
                sincronizar_empresa_dw(self.object)
                if codigo_anterior and codigo_anterior.upper() != self.object.empresa.upper():
                    remover_empresa_dw(codigo_anterior)
        except EmpresaDWError as err:
            form.add_error(None, str(err))
            return self.form_invalid(form)
        messages.success(self.request, 'Empresa atualizada com sucesso.')
        return redirect(self.get_success_url())


class EmpresaDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = Empresa
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:empresa_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'empresas'
        ctx['page_title'] = 'Excluir empresa'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:empresa_list')
        return ctx

    def form_valid(self, form):
        cd_empresa = self.object.empresa
        try:
            with transaction.atomic():
                remover_empresa_dw(cd_empresa)
                self.object.delete()
        except EmpresaDWError as err:
            messages.error(self.request, str(err))
            return redirect(self.get_success_url())
        messages.success(self.request, 'Empresa excluída.')
        return redirect(self.get_success_url())


class SocioListView(ControladoriaLayoutMixin, ListView):
    model = Socio
    template_name = 'controladoria/socio_list.html'
    context_object_name = 'socios'
    paginate_by = 25

    def get_queryset(self):
        qs = Socio.objects.prefetch_related('empresas__empresa')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nome__icontains=q)
                | Q(documento__icontains=q)
                | Q(email__icontains=q)
            )
        ativo = self.request.GET.get('ativo', '').strip()
        if ativo == '1':
            qs = qs.filter(ativo=True)
        elif ativo == '0':
            qs = qs.filter(ativo=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'socios'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['ativo'] = self.request.GET.get('ativo', '')
        return ctx


class SocioFormMixin:
    model = Socio
    form_class = SocioForm
    template_name = 'controladoria/socio_form.html'
    success_url = reverse_lazy('controladoria:socio_list')

    def get_formset(self):
        kwargs = {'instance': self.object}
        if self.request.method in ('POST', 'PUT'):
            kwargs['data'] = self.request.POST
        return SocioEmpresaFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'socios'
        if 'formset' not in ctx:
            ctx['formset'] = self.get_formset()
        return ctx

    def form_valid(self, form):
        formset = self.get_formset()
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

        messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        formset = self.get_formset()
        formset.is_valid()
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class SocioCreateView(SocioFormMixin, ControladoriaLayoutMixin, CreateView):
    success_message = 'Sócio cadastrado com sucesso.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Novo sócio'
        return ctx

    def get_formset(self):
        if self.request.method in ('POST', 'PUT'):
            return SocioEmpresaFormSet(self.request.POST, instance=Socio())
        return SocioEmpresaFormSet(instance=Socio())


class SocioUpdateView(SocioFormMixin, ControladoriaLayoutMixin, UpdateView):
    success_message = 'Sócio atualizado com sucesso.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Editar — {self.object.nome}'
        return ctx


class SocioDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = Socio
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:socio_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'socios'
        ctx['page_title'] = 'Excluir sócio'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:socio_list')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Sócio excluído.')
        return super().form_valid(form)


class CompetenciaListView(ControladoriaLayoutMixin, ListView):
    model = Competencia
    template_name = 'controladoria/competencia_list.html'
    context_object_name = 'competencias'
    paginate_by = 25

    def get_queryset(self):
        qs = Competencia.objects.select_related('tipo')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(tipo__nome__icontains=q))
        tipo = self.request.GET.get('tipo', '').strip()
        if tipo.isdigit():
            qs = qs.filter(tipo_id=int(tipo))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'competencias'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['tipo'] = self.request.GET.get('tipo', '')
        ctx['tipos'] = TipoCompetencia.objects.order_by('nome')
        return ctx


class CompetenciaCreateView(ControladoriaLayoutMixin, CreateView):
    model = Competencia
    form_class = CompetenciaForm
    template_name = 'controladoria/competencia_form.html'
    success_url = reverse_lazy('controladoria:competencia_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'competencias'
        ctx['page_title'] = 'Nova competência'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Competência cadastrada com sucesso.')
        return redirect(self.get_success_url())


class CompetenciaUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = Competencia
    form_class = CompetenciaForm
    template_name = 'controladoria/competencia_form.html'
    success_url = reverse_lazy('controladoria:competencia_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'competencias'
        ctx['page_title'] = f'Editar — {self.object}'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Competência atualizada com sucesso.')
        return redirect(self.get_success_url())


class CompetenciaDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = Competencia
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:competencia_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'competencias'
        ctx['page_title'] = 'Excluir competência'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:competencia_list')
        return ctx

    def form_valid(self, form):
        self.object.delete()
        messages.success(self.request, 'Competência excluída.')
        return redirect(self.get_success_url())


class ContaFinanceiraListView(ControladoriaLayoutMixin, ListView):
    model = ContaFinanceira
    template_name = 'controladoria/conta_financeira_list.html'
    context_object_name = 'contas'
    paginate_by = 25

    def get_queryset(self):
        qs = ContaFinanceira.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(descricao__icontains=q))
        tipo = self.request.GET.get('tipo', '').strip()
        if tipo in {TipoContaFinanceira.CREDITO, TipoContaFinanceira.DEBITO}:
            qs = qs.filter(tipo=tipo)
        ativo = self.request.GET.get('ativo', '').strip()
        if ativo == '1':
            qs = qs.filter(ativo=True)
        elif ativo == '0':
            qs = qs.filter(ativo=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'contas_financeiras'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['tipo'] = self.request.GET.get('tipo', '')
        ctx['ativo'] = self.request.GET.get('ativo', '')
        ctx['tipos_conta'] = TipoContaFinanceira.choices
        return ctx


class ContaFinanceiraCreateView(ControladoriaLayoutMixin, CreateView):
    model = ContaFinanceira
    form_class = ContaFinanceiraForm
    template_name = 'controladoria/conta_financeira_form.html'
    success_url = reverse_lazy('controladoria:conta_financeira_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'contas_financeiras'
        ctx['page_title'] = 'Nova conta financeira'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Conta financeira cadastrada com sucesso.')
        return redirect(self.get_success_url())


class ContaFinanceiraUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = ContaFinanceira
    form_class = ContaFinanceiraForm
    template_name = 'controladoria/conta_financeira_form.html'
    success_url = reverse_lazy('controladoria:conta_financeira_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'contas_financeiras'
        ctx['page_title'] = f'Editar — {self.object.nome}'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Conta financeira atualizada com sucesso.')
        return redirect(self.get_success_url())


class ContaFinanceiraDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = ContaFinanceira
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:conta_financeira_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'contas_financeiras'
        ctx['page_title'] = 'Excluir conta financeira'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:conta_financeira_list')
        return ctx

    def form_valid(self, form):
        if self.object.lancamentos.exists():
            messages.error(
                self.request,
                'Não é possível excluir: existem lançamentos vinculados a esta conta.',
            )
            return redirect(self.get_success_url())
        messages.success(self.request, 'Conta financeira excluída.')
        return super().form_valid(form)


class LancamentoFinanceiroListView(ControladoriaLayoutMixin, ListView):
    model = LancamentoFinanceiro
    template_name = 'controladoria/lancamento_list.html'
    context_object_name = 'lancamentos'
    paginate_by = 25

    def get_queryset(self):
        qs = LancamentoFinanceiro.objects.select_related(
            'conta', 'empreendimento', 'socio',
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(observacao__icontains=q)
                | Q(conta__nome__icontains=q)
                | Q(socio__nome__icontains=q)
                | Q(empreendimento__empresa__icontains=q)
                | Q(empreendimento__nome__icontains=q)
            )
        conta = self.request.GET.get('conta', '').strip()
        if conta.isdigit():
            qs = qs.filter(conta_id=int(conta))
        empreendimento = self.request.GET.get('empreendimento', '').strip()
        if empreendimento.isdigit():
            qs = qs.filter(empreendimento_id=int(empreendimento))
        socio = self.request.GET.get('socio', '').strip()
        if socio.isdigit():
            qs = qs.filter(socio_id=int(socio))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'lancamentos'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['conta'] = self.request.GET.get('conta', '')
        ctx['empreendimento'] = self.request.GET.get('empreendimento', '')
        ctx['socio'] = self.request.GET.get('socio', '')
        ctx['contas'] = ContaFinanceira.objects.order_by('nome')
        ctx['empreendimentos'] = Empresa.objects.order_by('empresa')
        ctx['socios'] = Socio.objects.order_by('nome')
        return ctx


class LancamentoFinanceiroCreateView(ControladoriaLayoutMixin, CreateView):
    model = LancamentoFinanceiro
    form_class = LancamentoFinanceiroForm
    template_name = 'controladoria/lancamento_form.html'
    success_url = reverse_lazy('controladoria:lancamento_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'lancamentos'
        ctx['page_title'] = 'Novo lançamento'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Lançamento cadastrado com sucesso.')
        return redirect(self.get_success_url())


class LancamentoFinanceiroUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = LancamentoFinanceiro
    form_class = LancamentoFinanceiroForm
    template_name = 'controladoria/lancamento_form.html'
    success_url = reverse_lazy('controladoria:lancamento_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'lancamentos'
        ctx['page_title'] = f'Editar lançamento — {self.object.pk}'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Lançamento atualizado com sucesso.')
        return redirect(self.get_success_url())


class LancamentoFinanceiroDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = LancamentoFinanceiro
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:lancamento_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'lancamentos'
        ctx['page_title'] = 'Excluir lançamento'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:lancamento_list')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Lançamento excluído.')
        return super().form_valid(form)


class ImovelVendidoListView(ControladoriaLayoutMixin, ListView):
    model = ImovelVendido
    template_name = 'controladoria/imovel_vendido_list.html'
    context_object_name = 'imoveis'
    paginate_by = 50

    def get_queryset(self):
        qs = ImovelVendido.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(contrato_ajustado__icontains=q)
                | Q(cliente__icontains=q)
                | Q(imovel__icontains=q)
                | Q(empreendimento_ajustado__icontains=q)
                | Q(cod_empreendimento__icontains=q)
                | Q(corretor__icontains=q)
                | Q(imobiliaria__icontains=q)
            )
        situacao = self.request.GET.get('situacao', '').strip()
        if situacao:
            qs = qs.filter(situacao__iexact=situacao)
        cod_empreendimento = self.request.GET.get('cod_empreendimento', '').strip()
        if cod_empreendimento:
            qs = qs.filter(cod_empreendimento__iexact=cod_empreendimento)
        regra_comissao = self.request.GET.get('regra_comissao', '').strip()
        if regra_comissao:
            qs = qs.filter(regra_comissao__iexact=regra_comissao)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'imoveis_vendidos'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['situacao'] = self.request.GET.get('situacao', '')
        ctx['cod_empreendimento'] = self.request.GET.get('cod_empreendimento', '')
        ctx['regra_comissao'] = self.request.GET.get('regra_comissao', '')
        ctx['situacoes'] = (
            ImovelVendido.objects.exclude(situacao='')
            .values_list('situacao', flat=True)
            .distinct()
            .order_by('situacao')
        )
        ctx['empreendimentos'] = (
            ImovelVendido.objects.exclude(cod_empreendimento='')
            .values_list('cod_empreendimento', flat=True)
            .distinct()
            .order_by('cod_empreendimento')
        )
        ctx['regras_comissao'] = (
            ImovelVendido.objects.exclude(regra_comissao='')
            .values_list('regra_comissao', flat=True)
            .distinct()
            .order_by('regra_comissao')
        )
        return ctx


class ImovelVendidoCreateView(ControladoriaLayoutMixin, CreateView):
    model = ImovelVendido
    form_class = ImovelVendidoForm
    template_name = 'controladoria/imovel_vendido_form.html'
    success_url = reverse_lazy('controladoria:imovel_vendido_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'imoveis_vendidos'
        ctx['page_title'] = 'Novo imóvel vendido'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Imóvel vendido cadastrado com sucesso.')
        return redirect(self.get_success_url())


class ImovelVendidoUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = ImovelVendido
    form_class = ImovelVendidoForm
    template_name = 'controladoria/imovel_vendido_form.html'
    success_url = reverse_lazy('controladoria:imovel_vendido_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'imoveis_vendidos'
        ctx['page_title'] = f'Editar — {self.object.contrato_ajustado}'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, 'Imóvel vendido atualizado com sucesso.')
        return redirect(self.get_success_url())


class ImovelVendidoDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = ImovelVendido
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:imovel_vendido_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'imoveis_vendidos'
        ctx['page_title'] = 'Excluir imóvel vendido'
        ctx['object_label'] = str(self.object)
        ctx['cancel_url'] = reverse('controladoria:imovel_vendido_list')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Imóvel vendido excluído.')
        return super().form_valid(form)


class ImovelVendidoImportView(ControladoriaLayoutMixin, View):
    template_name = 'controladoria/imovel_vendido_import.html'

    def get(self, request):
        return render(request, self.template_name, self._context(ImovelVendidoImportForm()))

    def post(self, request):
        form = ImovelVendidoImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form), status=400)

        try:
            resultado = importar_imoveis_vendidos(form.cleaned_data['arquivo'])
        except ImovelVendidoImportError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, self._context(form), status=400)

        messages.success(
            request,
            (
                f'Importação concluída: {resultado.criados} criados, '
                f'{resultado.atualizados} atualizados, {resultado.ignorados} sem alteração.'
            ),
        )
        return redirect('controladoria:imovel_vendido_list')

    def _context(self, form):
        return self.build_layout_context(
            form=form,
            nav_active='imoveis_vendidos',
            page_title='Importar imóveis vendidos',
        )


class MedidaListView(ControladoriaLayoutMixin, ListView):
    model = Medida
    template_name = 'controladoria/medida_list.html'
    context_object_name = 'medidas'
    paginate_by = 25

    def get_queryset(self):
        qs = Medida.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(codigo__icontains=q) | Q(nome__icontains=q))
        status = self.request.GET.get('status')
        if status == 'ativo':
            qs = qs.filter(ativo=True)
        elif status == 'inativo':
            qs = qs.filter(ativo=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'medidas'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['status'] = self.request.GET.get('status', '')
        return ctx


class MedidaCreateView(ControladoriaLayoutMixin, CreateView):
    model = Medida
    form_class = MedidaForm
    template_name = 'controladoria/medida_form.html'
    success_url = reverse_lazy('controladoria:medida_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'medidas'
        ctx['page_title'] = 'Nova medida'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Medida cadastrada com sucesso.')
        return super().form_valid(form)


class MedidaUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = Medida
    form_class = MedidaForm
    template_name = 'controladoria/medida_form.html'
    success_url = reverse_lazy('controladoria:medida_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'medidas'
        ctx['page_title'] = f'Editar — {self.object.codigo}'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Medida atualizada com sucesso.')
        return super().form_valid(form)


class MedidaDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = Medida
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:medida_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'medidas'
        ctx['page_title'] = 'Excluir medida'
        ctx['object_label'] = self.object.codigo
        ctx['cancel_url'] = reverse('controladoria:medida_list')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Medida excluída.')
        return super().form_valid(form)


class RegraListView(ControladoriaLayoutMixin, ListView):
    model = RegraMedida
    template_name = 'controladoria/regra_list.html'
    context_object_name = 'regras'
    paginate_by = 25

    def get_queryset(self):
        qs = RegraMedida.objects.select_related('medida')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(medida__codigo__icontains=q))
        medida_id = self.request.GET.get('medida')
        if medida_id:
            qs = qs.filter(medida_id=medida_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'regras'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['medida_filter'] = self.request.GET.get('medida', '')
        ctx['medidas'] = Medida.objects.filter(ativo=True)
        return ctx


class RegraFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'POST':
            kwargs['condicoes_post'] = condicoes_from_post(self.request.POST)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = ctx.get('form') or self.get_form()
        ctx['filtros_grupos'] = form.get_filtros_grupos()
        ctx['campos_fato'] = campos_filtro()
        ctx['operadores'] = OperadorFiltro.choices
        ctx['operador_raiz_choices'] = OPERADOR_RAIZ_CHOICES
        return ctx


class RegraCreateView(RegraFormMixin, ControladoriaLayoutMixin, CreateView):
    model = RegraMedida
    form_class = RegraMedidaForm
    template_name = 'controladoria/regra_form.html'
    success_url = reverse_lazy('controladoria:regra_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'regras'
        ctx['page_title'] = 'Nova regra'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Regra cadastrada com sucesso.')
        return super().form_valid(form)


class RegraUpdateView(RegraFormMixin, ControladoriaLayoutMixin, UpdateView):
    model = RegraMedida
    form_class = RegraMedidaForm
    template_name = 'controladoria/regra_form.html'
    success_url = reverse_lazy('controladoria:regra_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'regras'
        ctx['page_title'] = f'Editar — {self.object.nome}'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Regra atualizada com sucesso.')
        return super().form_valid(form)


class RegraDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = RegraMedida
    template_name = 'controladoria/confirm_delete.html'
    success_url = reverse_lazy('controladoria:regra_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'regras'
        ctx['page_title'] = 'Excluir regra'
        ctx['object_label'] = self.object.nome
        ctx['cancel_url'] = reverse('controladoria:regra_list')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Regra excluída.')
        return super().form_valid(form)


class RegraPreviewView(ControladoriaLayoutMixin, TemplateView):
    template_name = 'controladoria/preview_regra.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'regras'
        regra = get_object_or_404(RegraMedida.objects.select_related('medida'), pk=kwargs['pk'])
        ctx['regra'] = regra
        ctx['preview'] = None
        ctx['erro'] = None
        try:
            ctx['preview'] = preview_regra(regra.pk)
        except MotorRegrasError as exc:
            ctx['erro'] = str(exc)
        return ctx


def _query_filtros(**params) -> str:
    return urlencode({k: v for k, v in params.items() if v not in (None, '')})


def _query_excecao_list(**params) -> str:
    return _query_filtros(**params)


class ExcecaoExplorarView(ControladoriaLayoutMixin, TemplateView):
    template_name = 'controladoria/excecao_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'excecoes'
        medidas_com_regra = RegraMedida.objects.filter(ativo=True).values('medida_id')
        ctx['medidas'] = (
            Medida.objects.filter(ativo=True, pk__in=medidas_com_regra)
            .order_by('ordem', 'codigo')
        )
        ctx['medida_id'] = self.request.GET.get('medida', '')
        ctx['regra_id'] = self.request.GET.get('regra', '')
        ctx['q'] = self.request.GET.get('q', '').strip()
        data_inicio, data_fim, status_lancamento = _parse_filtros_lancamentos(
            self.request.GET.get('data_inicio', '').strip(),
            self.request.GET.get('data_fim', '').strip(),
            self.request.GET.get('status', 'todos'),
        )
        ctx['status_lancamento'] = status_lancamento
        ctx['data_inicio'] = data_inicio.isoformat()
        ctx['data_fim'] = data_fim.isoformat()
        ctx['pagina'] = max(int(self.request.GET.get('page', 1) or 1), 1)
        tab = self.request.GET.get('tab', 'lancamentos')
        ctx['tab_ativa'] = tab if tab in ('lancamentos', 'excecoes') else 'lancamentos'
        ctx['regras'] = []
        ctx['regra'] = None
        ctx['resultado'] = None
        ctx['erro'] = None
        ctx['excecoes_cadastradas'] = []

        if not ctx['medida_id']:
            return ctx

        try:
            medida_id = int(ctx['medida_id'])
        except ValueError:
            ctx['erro'] = 'Medida inválida.'
            return ctx

        ctx['regras'] = obter_regras_medida(medida_id)
        if not ctx['regras']:
            ctx['erro'] = 'Nenhuma regra ativa cadastrada para esta medida.'
            return ctx

        regra = None
        if ctx['regra_id']:
            try:
                regra = next(r for r in ctx['regras'] if r.pk == int(ctx['regra_id']))
            except (StopIteration, ValueError):
                regra = None
        if not regra:
            regra = ctx['regras'][0]
            ctx['regra_id'] = str(regra.pk)

        ctx['regra'] = regra
        ctx['tem_subgrupo'] = campo_na_listagem('nmSubGrupo')
        ctx['excecoes_cadastradas'] = list(
            regra.excecoes.filter(ativo=True).select_related('regra').order_by('-criado_em')
        )
        ctx['query_lancamentos'] = _query_excecao_list(
            medida=ctx['medida_id'],
            regra=ctx['regra_id'],
            q=ctx['q'],
            data_inicio=ctx['data_inicio'],
            data_fim=ctx['data_fim'],
            status=ctx['status_lancamento'],
            tab='lancamentos',
        )
        ctx['query_excecoes'] = _query_excecao_list(
            medida=ctx['medida_id'],
            regra=ctx['regra_id'],
            tab='excecoes',
        )

        try:
            ctx['resultado'] = buscar_lancamentos_regra(
                regra,
                pagina=ctx['pagina'],
                busca=ctx['q'],
                data_inicio=data_inicio,
                data_fim=data_fim,
                status=status_lancamento,
            )
        except MotorRegrasError as exc:
            ctx['erro'] = str(exc)

        return ctx


@login_required
@require_POST
def excecao_adicionar_lancamento(request):
    regra = get_object_or_404(RegraMedida.objects.select_related('medida'), pk=request.POST.get('regra_id'))
    try:
        criar_excecao_lancamento(regra, request.POST)
        messages.success(request, 'Lançamento excluído da regra (adicionado às exceções).')
    except MotorRegrasError as exc:
        messages.warning(request, str(exc))

    params = urlencode({
        'medida': regra.medida_id,
        'regra': regra.pk,
        'q': request.POST.get('q_retorno', ''),
        'page': request.POST.get('page_retorno', '1'),
        'data_inicio': request.POST.get('data_inicio_retorno', ''),
        'data_fim': request.POST.get('data_fim_retorno', ''),
        'status': request.POST.get('status_retorno', 'todos'),
        'tab': 'lancamentos',
    })
    return redirect(f"{reverse('controladoria:excecao_list')}?{params}")


class ExcecaoCreateView(ControladoriaLayoutMixin, CreateView):
    model = ExcecaoLancamento
    form_class = ExcecaoLancamentoForm
    template_name = 'controladoria/excecao_form.html'
    success_url = reverse_lazy('controladoria:excecao_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'excecoes'
        ctx['page_title'] = 'Nova exceção'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Exceção cadastrada com sucesso.')
        return super().form_valid(form)


class ExcecaoUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = ExcecaoLancamento
    form_class = ExcecaoLancamentoForm
    template_name = 'controladoria/excecao_form.html'
    success_url = reverse_lazy('controladoria:excecao_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'excecoes'
        ctx['page_title'] = 'Editar exceção'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Exceção atualizada com sucesso.')
        return super().form_valid(form)


class ExcecaoDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = ExcecaoLancamento
    template_name = 'controladoria/confirm_delete.html'

    def get_success_url(self):
        exc = self.object
        params = urlencode({
            'medida': exc.regra.medida_id,
            'regra': exc.regra_id,
            'tab': 'excecoes',
        })
        return f"{reverse('controladoria:excecao_list')}?{params}"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'excecoes'
        ctx['page_title'] = 'Remover exceção'
        ctx['object_label'] = str(self.object)
        medida = self.request.GET.get('medida', self.object.regra.medida_id)
        regra = self.request.GET.get('regra', self.object.regra_id)
        ctx['cancel_url'] = (
            f"{reverse('controladoria:excecao_list')}?medida={medida}&regra={regra}&tab=excecoes"
        )
        return ctx

    def form_valid(self, form):
        try:
            excluir_excecao_lancamento(self.object)
        except MotorRegrasError as exc:
            messages.error(self.request, str(exc))
            params = urlencode({
                'medida': self.object.regra.medida_id,
                'regra': self.object.regra_id,
                'tab': 'excecoes',
            })
            return redirect(f"{reverse('controladoria:excecao_list')}?{params}")
        messages.success(
            self.request,
            'Exceção removida. O lançamento voltará a entrar na regra.',
        )
        return redirect(self.get_success_url())


class AjusteExplorarView(ControladoriaLayoutMixin, TemplateView):
    template_name = 'controladoria/ajuste_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'ajustes'
        medidas_com_regra = RegraMedida.objects.filter(ativo=True).values('medida_id')
        ctx['medidas'] = (
            Medida.objects.filter(ativo=True, pk__in=medidas_com_regra)
            .order_by('ordem', 'codigo')
        )
        ctx['medida_id'] = self.request.GET.get('medida', '')
        ctx['regra_id'] = self.request.GET.get('regra', '')
        ctx['q'] = self.request.GET.get('q', '').strip()
        data_inicio, data_fim, _ = _parse_filtros_lancamentos(
            self.request.GET.get('data_inicio', '').strip(),
            self.request.GET.get('data_fim', '').strip(),
            'todos',
        )
        ctx['data_inicio'] = data_inicio.isoformat()
        ctx['data_fim'] = data_fim.isoformat()
        ctx['pagina'] = max(int(self.request.GET.get('page', 1) or 1), 1)
        tab = self.request.GET.get('tab', 'lancamentos')
        ctx['tab_ativa'] = tab if tab in ('lancamentos', 'ajustes') else 'lancamentos'
        ctx['regras'] = []
        ctx['regra'] = None
        ctx['resultado'] = None
        ctx['erro'] = None
        ctx['ajustes_cadastrados'] = []

        if not ctx['medida_id']:
            return ctx

        try:
            medida_id = int(ctx['medida_id'])
        except ValueError:
            ctx['erro'] = 'Medida inválida.'
            return ctx

        ctx['regras'] = obter_regras_medida(medida_id)
        if not ctx['regras']:
            ctx['erro'] = 'Nenhuma regra ativa cadastrada para esta medida.'
            return ctx

        regra = None
        if ctx['regra_id']:
            try:
                regra = next(r for r in ctx['regras'] if r.pk == int(ctx['regra_id']))
            except (StopIteration, ValueError):
                regra = None
        if not regra:
            regra = ctx['regras'][0]
            ctx['regra_id'] = str(regra.pk)

        ctx['regra'] = regra
        ctx['tem_subgrupo'] = campo_na_listagem('nmSubGrupo')
        ctx['ajustes_cadastrados'] = list(
            AjusteManual.objects.filter(medida=regra.medida, ativo=True)
            .select_related('medida')
            .order_by('-criado_em')
        )
        ctx['query_lancamentos'] = _query_filtros(
            medida=ctx['medida_id'],
            regra=ctx['regra_id'],
            q=ctx['q'],
            data_inicio=ctx['data_inicio'],
            data_fim=ctx['data_fim'],
            tab='lancamentos',
        )
        ctx['query_ajustes'] = _query_filtros(
            medida=ctx['medida_id'],
            regra=ctx['regra_id'],
            tab='ajustes',
        )

        try:
            ctx['resultado'] = buscar_lancamentos_excluidos(
                regra,
                pagina=ctx['pagina'],
                busca=ctx['q'],
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        except MotorRegrasError as exc:
            ctx['erro'] = str(exc)

        return ctx


class AjusteGerarView(ControladoriaLayoutMixin, View):
    template_name = 'controladoria/ajuste_gerar.html'

    def _cancel_url(self, data) -> str:
        params = _query_filtros(
            medida=data.get('medida_id'),
            regra=data.get('regra_id'),
            q=data.get('q_retorno', ''),
            page=data.get('page_retorno', '1'),
            data_inicio=data.get('data_inicio_retorno', ''),
            data_fim=data.get('data_fim_retorno', ''),
            tab='lancamentos',
        )
        return f"{reverse('controladoria:ajuste_list')}?{params}"

    def _initial_form(self, data) -> dict:
        lanc = dados_lancamento_from_request(data)
        data_val = lanc.get('data')
        return {
            'medida_id': data.get('medida_id'),
            'regra_id': data.get('regra_id'),
            'chave_orc': lanc.get('chave_orc', ''),
            'cd_empresa': lanc.get('cd_empresa', ''),
            'cd_empreendimento': lanc.get('cd_empreendimento', ''),
            'cd_nucleo': lanc.get('cd_nucleo', ''),
            'cd_centro': lanc.get('cd_centro', ''),
            'assunto': lanc.get('assunto', ''),
            'classificacao': lanc.get('classificacao', ''),
            'cliente_fornecedor': lanc.get('cliente_fornecedor', ''),
            'data_competencia': data_val,
            'valor': lanc.get('valor'),
            'data_original': data_val,
            'valor_original': lanc.get('valor'),
            'q_retorno': data.get('q_retorno', ''),
            'page_retorno': data.get('page_retorno', '1'),
            'data_inicio_retorno': data.get('data_inicio_retorno', ''),
            'data_fim_retorno': data.get('data_fim_retorno', ''),
        }

    def _form_kwargs(self, regra, data) -> dict:
        lanc = dados_lancamento_from_request(data)
        resumo = resumo_ajustes_lancamento(regra.medida, lanc)
        return {
            'initial': self._initial_form(data),
            'resumo_ajustes': resumo,
        }

    def get(self, request, *args, **kwargs):
        regra = get_object_or_404(
            RegraMedida.objects.select_related('medida'),
            pk=request.GET.get('regra_id'),
        )
        lancamento = dados_lancamento_from_request(request.GET)
        lancamento['dc'] = request.GET.get('dc', '')
        resumo = resumo_ajustes_lancamento(regra.medida, lancamento)
        ctx = self.build_layout_context(
            nav_active='ajustes',
            page_title='Gerar lançamento',
            regra=regra,
            medida=regra.medida,
            lancamento=lancamento,
            resumo_ajustes=resumo,
            cancel_url=self._cancel_url(request.GET),
            form=AjusteGerarLancamentoForm(**self._form_kwargs(regra, request.GET)),
        )
        return render(request, self.template_name, ctx)

    def post(self, request, *args, **kwargs):
        regra = get_object_or_404(
            RegraMedida.objects.select_related('medida'),
            pk=request.POST.get('regra_id'),
        )
        lancamento = dados_lancamento_from_request({**request.GET.dict(), **request.POST.dict()})
        lancamento['dc'] = request.POST.get('dc', '')
        resumo = resumo_ajustes_lancamento(regra.medida, lancamento)
        form = AjusteGerarLancamentoForm(
            request.POST,
            resumo_ajustes=resumo,
        )
        cancel_url = self._cancel_url(request.POST)

        if form.is_valid():
            try:
                criar_ajuste_lancamento(
                    regra.medida,
                    regra,
                    {**form.cleaned_data, **request.POST.dict()},
                )
                messages.success(request, 'Ajuste gerado com sucesso.')
                return redirect(cancel_url)
            except MotorRegrasError as exc:
                messages.error(request, str(exc))

        ctx = self.build_layout_context(
            nav_active='ajustes',
            page_title='Gerar lançamento',
            regra=regra,
            medida=regra.medida,
            lancamento=lancamento,
            resumo_ajustes=resumo,
            cancel_url=cancel_url,
            form=form,
        )
        return render(request, self.template_name, ctx)


class AjusteCreateView(ControladoriaLayoutMixin, CreateView):
    model = AjusteManual
    form_class = AjusteManualForm
    template_name = 'controladoria/ajuste_form.html'
    success_url = reverse_lazy('controladoria:ajuste_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'ajustes'
        ctx['page_title'] = 'Novo ajuste manual'
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        try:
            inserir_ajuste_dw(self.object)
        except AjusteDWError as exc:
            self.object.delete()
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, 'Ajuste cadastrado com sucesso.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('controladoria:ajuste_list')


class AjusteUpdateView(ControladoriaLayoutMixin, UpdateView):
    model = AjusteManual
    form_class = AjusteEditForm
    template_name = 'controladoria/ajuste_form.html'

    def get_success_url(self):
        retorno = self.request.GET.get('retorno')
        if retorno:
            return f"{reverse('controladoria:ajuste_list')}?{retorno}"
        return reverse_lazy('controladoria:ajuste_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'ajustes'
        ctx['page_title'] = 'Editar ajuste manual'
        retorno = self.request.GET.get('retorno', '')
        ctx['cancel_url'] = (
            f"{reverse('controladoria:ajuste_list')}?{retorno}" if retorno
            else reverse('controladoria:ajuste_list')
        )
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            atualizar_ajuste_dw(self.object)
        except AjusteDWError as exc:
            messages.error(self.request, str(exc))
        else:
            messages.success(self.request, 'Ajuste atualizado com sucesso.')
        return response


class AjusteDeleteView(ControladoriaLayoutMixin, DeleteView):
    model = AjusteManual
    template_name = 'controladoria/confirm_delete.html'

    def get_success_url(self):
        retorno = self.request.GET.get('retorno')
        if retorno:
            return f"{reverse('controladoria:ajuste_list')}?{retorno}"
        return reverse_lazy('controladoria:ajuste_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'ajustes'
        ctx['page_title'] = 'Excluir ajuste'
        ctx['object_label'] = str(self.object)
        retorno = self.request.GET.get('retorno', '')
        ctx['cancel_url'] = (
            f"{reverse('controladoria:ajuste_list')}?{retorno}" if retorno
            else reverse('controladoria:ajuste_list')
        )
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Ajuste excluído.')
        return super().form_valid(form)


def _parse_filtros_comissao(data_corte_str: str, mes_str: str, ano_str: str):
    from datetime import date

    data_corte = None
    if data_corte_str:
        try:
            data_corte = date.fromisoformat(data_corte_str)
        except ValueError:
            pass

    mes = None
    ano = None
    if mes_str.isdigit():
        mes = int(mes_str)
    if ano_str.isdigit():
        ano = int(ano_str)

    if (mes and not ano) or (ano and not mes):
        raise ComissaoError('Informe mês e ano de fechamento juntos, ou deixe ambos em branco.')

    if mes is not None and not (1 <= mes <= 12):
        raise ComissaoError('Mês de fechamento inválido.')

    return data_corte, mes, ano


def _query_comissao_list(**params) -> str:
    clean = {k: v for k, v in params.items() if v not in (None, '')}
    return urlencode(clean)


def _redirect_comissao_list(request, tab: str = 'consulta') -> str:
    params = {
        'data_corte': request.POST.get('data_corte_retorno', '').strip(),
        'mes_fechamento': request.POST.get('mes_fechamento_retorno', '').strip(),
        'ano_fechamento': request.POST.get('ano_fechamento_retorno', '').strip(),
        'status_elegibilidade': request.POST.get('status_elegibilidade_retorno', 'todos'),
        'tab': tab,
        'page': request.POST.get('page_retorno', '1'),
    }
    return f"{reverse('controladoria:comissao_list')}?{_query_comissao_list(**params)}"


class ComissaoGestaoView(ControladoriaLayoutMixin, TemplateView):
    template_name = 'controladoria/comissao_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_active'] = 'comissoes'
        ctx['data_corte'] = self.request.GET.get('data_corte', '').strip()
        ctx['mes_fechamento'] = self.request.GET.get('mes_fechamento', '').strip()
        ctx['ano_fechamento'] = self.request.GET.get('ano_fechamento', '').strip()
        status = self.request.GET.get('status_elegibilidade', 'todos').strip()
        ctx['status_elegibilidade'] = status if status in ('todos', 'atingiu', 'nao_atingiu') else 'todos'
        ctx['pagina'] = max(int(self.request.GET.get('page', 1) or 1), 1)
        tab = self.request.GET.get('tab', 'consulta')
        ctx['tab_ativa'] = tab if tab in ('consulta', 'incluidas') else 'consulta'
        ctx['resultado'] = None
        ctx['erro'] = None
        ctx['comissoes_incluidas'] = (
            Comissao.objects.select_related('criado_por')
            .order_by('-criado_em')[:200]
        )
        ctx['query_consulta'] = _query_comissao_list(
            data_corte=ctx['data_corte'],
            mes_fechamento=ctx['mes_fechamento'],
            ano_fechamento=ctx['ano_fechamento'],
            status_elegibilidade=ctx['status_elegibilidade'],
            tab='consulta',
        )
        ctx['query_incluidas'] = _query_comissao_list(
            data_corte=ctx['data_corte'],
            mes_fechamento=ctx['mes_fechamento'],
            ano_fechamento=ctx['ano_fechamento'],
            status_elegibilidade=ctx['status_elegibilidade'],
            tab='incluidas',
        )

        if not ctx['data_corte']:
            return ctx

        try:
            data_corte, mes, ano = _parse_filtros_comissao(
                ctx['data_corte'],
                ctx['mes_fechamento'],
                ctx['ano_fechamento'],
            )
            if not data_corte:
                ctx['erro'] = 'Informe a data de corte.'
                return ctx
            ctx['resultado'] = buscar_comissoes_dw(
                data_corte=data_corte,
                mes_fechamento=mes,
                ano_fechamento=ano,
                pagina=ctx['pagina'],
                status_elegibilidade=ctx['status_elegibilidade'],
            )
            ctx['pagina'] = ctx['resultado']['pagina']
        except ComissaoError as exc:
            ctx['erro'] = str(exc)

        return ctx


@login_required
@require_POST
def comissao_incluir(request):
    data_corte_str = request.POST.get('data_corte', '').strip()
    mes_str = request.POST.get('mes_fechamento', '').strip()
    ano_str = request.POST.get('ano_fechamento', '').strip()
    data_pagamento_str = request.POST.get('data_pagamento', '').strip()

    params = {
        'data_corte': data_corte_str,
        'mes_fechamento': mes_str,
        'ano_fechamento': ano_str,
        'status_elegibilidade': request.POST.get('status_elegibilidade_retorno', 'todos'),
        'tab': 'consulta',
        'page': request.POST.get('page_retorno', '1'),
    }
    redirect_url = f"{reverse('controladoria:comissao_list')}?{_query_comissao_list(**params)}"

    try:
        from datetime import date

        data_corte, mes, ano = _parse_filtros_comissao(data_corte_str, mes_str, ano_str)
        if not data_corte:
            raise ComissaoError('Informe a data de corte.')
        try:
            data_pagamento = date.fromisoformat(data_pagamento_str)
        except ValueError as exc:
            raise ComissaoError('Informe uma data de pagamento válida.') from exc
        incluir_comissao(
            dados=request.POST,
            data_pagamento=data_pagamento,
            data_corte=data_corte,
            mes_fechamento=mes,
            ano_fechamento=ano,
            usuario=request.user,
        )
        messages.success(request, 'Comissão incluída para pagamento.')
    except ComissaoError as exc:
        messages.warning(request, str(exc))

    return redirect(redirect_url)


@login_required
@require_POST
def comissao_atualizar_pagamento(request, pk):
    redirect_url = _redirect_comissao_list(request, tab='incluidas')
    data_pagamento_str = request.POST.get('data_pagamento', '').strip()

    try:
        from datetime import date

        try:
            data_pagamento = date.fromisoformat(data_pagamento_str)
        except ValueError as exc:
            raise ComissaoError('Informe uma data de pagamento válida.') from exc
        atualizar_data_pagamento(pk, data_pagamento)
        messages.success(request, 'Data de pagamento atualizada.')
    except ComissaoError as exc:
        messages.warning(request, str(exc))

    return redirect(redirect_url)


@login_required
@require_POST
def comissao_excluir(request, pk):
    redirect_url = _redirect_comissao_list(request, tab='incluidas')

    try:
        excluir_comissao(pk)
        messages.success(request, 'Comissão excluída. O contrato voltará a aparecer na consulta DW.')
    except ComissaoError as exc:
        messages.warning(request, str(exc))

    return redirect(redirect_url)
