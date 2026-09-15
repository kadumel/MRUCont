from django.urls import path
from django.views.generic.base import RedirectView

from controladoria import views

app_name = 'controladoria'

urlpatterns = [
    path('login/', views.PortalLoginView.as_view(), name='login'),
    path('logout/', views.portal_logout, name='logout'),
    path('', views.MedidaListView.as_view(), name='medida_list'),
    path('inicio/', views.DashboardView.as_view(), name='dashboard'),

    path('cadastros/empresas/', views.EmpresaListView.as_view(), name='empresa_list'),
    path('cadastros/empresas/nova/', views.EmpresaCreateView.as_view(), name='empresa_create'),
    path('cadastros/empresas/<int:pk>/editar/', views.EmpresaUpdateView.as_view(), name='empresa_edit'),
    path('cadastros/empresas/<int:pk>/excluir/', views.EmpresaDeleteView.as_view(), name='empresa_delete'),

    path('cadastros/socios/', views.SocioListView.as_view(), name='socio_list'),
    path('cadastros/socios/novo/', views.SocioCreateView.as_view(), name='socio_create'),
    path('cadastros/socios/<int:pk>/editar/', views.SocioUpdateView.as_view(), name='socio_edit'),
    path('cadastros/socios/<int:pk>/excluir/', views.SocioDeleteView.as_view(), name='socio_delete'),

    path('cadastros/competencias/', views.CompetenciaListView.as_view(), name='competencia_list'),
    path('cadastros/competencias/nova/', views.CompetenciaCreateView.as_view(), name='competencia_create'),
    path('cadastros/competencias/<int:pk>/editar/', views.CompetenciaUpdateView.as_view(), name='competencia_edit'),
    path('cadastros/competencias/<int:pk>/excluir/', views.CompetenciaDeleteView.as_view(), name='competencia_delete'),

    path('cadastros/contas-financeiras/', views.ContaFinanceiraListView.as_view(), name='conta_financeira_list'),
    path('cadastros/contas-financeiras/nova/', views.ContaFinanceiraCreateView.as_view(), name='conta_financeira_create'),
    path('cadastros/contas-financeiras/<int:pk>/editar/', views.ContaFinanceiraUpdateView.as_view(), name='conta_financeira_edit'),
    path('cadastros/contas-financeiras/<int:pk>/excluir/', views.ContaFinanceiraDeleteView.as_view(), name='conta_financeira_delete'),

    path('movimentos/lancamentos/', views.LancamentoFinanceiroListView.as_view(), name='lancamento_list'),
    path('movimentos/lancamentos/novo/', views.LancamentoFinanceiroCreateView.as_view(), name='lancamento_create'),
    path('movimentos/lancamentos/<int:pk>/editar/', views.LancamentoFinanceiroUpdateView.as_view(), name='lancamento_edit'),
    path('movimentos/lancamentos/<int:pk>/excluir/', views.LancamentoFinanceiroDeleteView.as_view(), name='lancamento_delete'),

    path('movimentos/imoveis-vendidos/', views.ImovelVendidoListView.as_view(), name='imovel_vendido_list'),
    path('movimentos/imoveis-vendidos/novo/', views.ImovelVendidoCreateView.as_view(), name='imovel_vendido_create'),
    path('movimentos/imoveis-vendidos/importar/', views.ImovelVendidoImportView.as_view(), name='imovel_vendido_import'),
    path('movimentos/imoveis-vendidos/<int:pk>/editar/', views.ImovelVendidoUpdateView.as_view(), name='imovel_vendido_edit'),
    path('movimentos/imoveis-vendidos/<int:pk>/excluir/', views.ImovelVendidoDeleteView.as_view(), name='imovel_vendido_delete'),

    path('medidas/', RedirectView.as_view(pattern_name='controladoria:medida_list', permanent=False)),
    path('medidas/nova/', views.MedidaCreateView.as_view(), name='medida_create'),
    path('medidas/<int:pk>/editar/', views.MedidaUpdateView.as_view(), name='medida_edit'),
    path('medidas/<int:pk>/excluir/', views.MedidaDeleteView.as_view(), name='medida_delete'),

    path('regras/', views.RegraListView.as_view(), name='regra_list'),
    path('regras/nova/', views.RegraCreateView.as_view(), name='regra_create'),
    path('regras/<int:pk>/editar/', views.RegraUpdateView.as_view(), name='regra_edit'),
    path('regras/<int:pk>/excluir/', views.RegraDeleteView.as_view(), name='regra_delete'),
    path('regras/<int:pk>/preview/', views.RegraPreviewView.as_view(), name='regra_preview'),

    path('excecoes/', views.ExcecaoExplorarView.as_view(), name='excecao_list'),
    path('excecoes/adicionar/', views.excecao_adicionar_lancamento, name='excecao_adicionar'),
    path('excecoes/nova/', views.ExcecaoCreateView.as_view(), name='excecao_create'),
    path('excecoes/<int:pk>/editar/', views.ExcecaoUpdateView.as_view(), name='excecao_edit'),
    path('excecoes/<int:pk>/excluir/', views.ExcecaoDeleteView.as_view(), name='excecao_delete'),

    path('ajustes/', views.AjusteExplorarView.as_view(), name='ajuste_list'),
    path('ajustes/gerar/', views.AjusteGerarView.as_view(), name='ajuste_gerar'),
    path('ajustes/novo/', views.AjusteCreateView.as_view(), name='ajuste_create'),
    path('ajustes/<int:pk>/editar/', views.AjusteUpdateView.as_view(), name='ajuste_edit'),
    path('ajustes/<int:pk>/excluir/', views.AjusteDeleteView.as_view(), name='ajuste_delete'),

    path('comissoes/', views.ComissaoGestaoView.as_view(), name='comissao_list'),
    path('comissoes/incluir/', views.comissao_incluir, name='comissao_incluir'),
    path('comissoes/<int:pk>/pagamento/', views.comissao_atualizar_pagamento, name='comissao_atualizar_pagamento'),
    path('comissoes/<int:pk>/excluir/', views.comissao_excluir, name='comissao_excluir'),
]
