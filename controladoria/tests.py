from datetime import date

from django.test import TestCase

from controladoria.models import AjusteManual, Medida, TipoAjuste
from controladoria.services.ajustes import (
    soma_ajustes_lancamento,
    validar_soma_ajustes,
    valor_restante_ajustes,
)
from controladoria.services.consulta_base import campos_filtro, resolver_campo_sql
from controladoria.services.layout import apply_nav_sidebar_context
from controladoria.services.motor_regras import MotorRegrasError


class ValidacaoSomaAjustesTests(TestCase):
    def test_valor_restante_positivo(self):
        self.assertEqual(valor_restante_ajustes(1000.0, 400.0), 600.0)

    def test_valor_restante_negativo(self):
        self.assertEqual(valor_restante_ajustes(-1000.0, -400.0), -600.0)

    def test_permite_soma_igual_ao_original(self):
        validar_soma_ajustes(1000.0, 600.0, 400.0)

    def test_bloqueia_soma_acima_do_original_positivo(self):
        with self.assertRaises(MotorRegrasError):
            validar_soma_ajustes(1000.0, 600.0, 500.0)

    def test_bloqueia_soma_abaixo_do_original_negativo(self):
        with self.assertRaises(MotorRegrasError):
            validar_soma_ajustes(-1000.0, -600.0, -500.0)

    def test_soma_ajustes_vinculados(self):
        medida = Medida.objects.create(codigo='MedTeste', nome='Medida teste', ordem=1)
        row = {
            'chave_orc': 'CH-1',
            'cd_empresa': '001',
            'cd_empreendimento': 'EMP1',
            'cd_nucleo': '',
            'cd_centro': '',
            'data': date(2024, 6, 15),
            'valor': 1000.0,
        }
        AjusteManual.objects.create(
            medida=medida,
            tipo=TipoAjuste.RECLASSIFICACAO,
            cd_empresa='001',
            cd_empreendimento='EMP1',
            data_competencia=date(2024, 7, 31),
            data_lancamento=date(2024, 7, 31),
            data_original=date(2024, 6, 15),
            valor=400.0,
            valor_original=1000.0,
            chave_orc='CH-1',
            ativo=True,
        )
        AjusteManual.objects.create(
            medida=medida,
            tipo=TipoAjuste.RECLASSIFICACAO,
            cd_empresa='001',
            cd_empreendimento='EMP1',
            data_competencia=date(2024, 8, 31),
            data_lancamento=date(2024, 8, 31),
            data_original=date(2024, 6, 15),
            valor=300.0,
            valor_original=1000.0,
            chave_orc='CH-1',
            ativo=True,
        )
        self.assertEqual(soma_ajustes_lancamento(medida, row), 700.0)
        validar_soma_ajustes(1000.0, 700.0, 300.0)
        with self.assertRaises(MotorRegrasError):
            validar_soma_ajustes(1000.0, 700.0, 301.0)


class NavSidebarContextTests(TestCase):
    def test_expande_menu_regras_quando_nav_active_definido(self):
        ctx = {'nav_active': 'ajustes'}
        apply_nav_sidebar_context(ctx)
        self.assertTrue(ctx['nav_regras_expanded'])
        self.assertFalse(ctx['nav_cadastros_expanded'])

    def test_expande_menu_cadastros_para_empresas(self):
        ctx = {'nav_active': 'empresas'}
        apply_nav_sidebar_context(ctx)
        self.assertTrue(ctx['nav_cadastros_expanded'])
        self.assertFalse(ctx['nav_regras_expanded'])

    def test_expande_menu_cadastros_para_competencias(self):
        ctx = {'nav_active': 'competencias'}
        apply_nav_sidebar_context(ctx)
        self.assertTrue(ctx['nav_cadastros_expanded'])
        self.assertFalse(ctx['nav_regras_expanded'])

    def test_expande_menu_movimentos_para_imoveis_vendidos(self):
        ctx = {'nav_active': 'imoveis_vendidos'}
        apply_nav_sidebar_context(ctx)
        self.assertTrue(ctx['nav_movimentos_expanded'])
        self.assertFalse(ctx['nav_cadastros_expanded'])
        self.assertFalse(ctx['nav_regras_expanded'])


class ConsultaBaseTests(TestCase):
    def test_campo_filtravel_e_sql(self):
        ids = [c[0] for c in campos_filtro()]
        self.assertIn('Assunto', ids)
        self.assertIn('Segmento', ids)
