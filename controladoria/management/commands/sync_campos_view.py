"""Recarrega colunas da VIEW do DW."""

from django.core.management.base import BaseCommand

from controladoria.services.consulta_base import (
    campos_filtro,
    get_campos_consulta,
    limpar_cache_campos,
    origem_campos_consulta,
)


class Command(BaseCommand):
    help = 'Recarrega automaticamente as colunas de VW_Q12_SISTEMA (ou FONTE_REGRAS_TABELA).'

    def handle(self, *args, **options):
        limpar_cache_campos()
        campos = get_campos_consulta(force_refresh=True)
        origem = origem_campos_consulta()

        self.stdout.write(self.style.SUCCESS(f'{len(campos)} coluna(s) carregada(s) — origem: {origem}'))
        for campo in campos:
            flags = []
            if campo.filtravel:
                flags.append('filtro')
            if campo.listagem:
                flags.append('lista')
            if campo.agregavel:
                flags.append('agrega')
            if campo.busca:
                flags.append('busca')
            self.stdout.write(f'  - {campo.id} ({", ".join(flags) or "—"})')

        self.stdout.write(self.style.MIGRATE_HEADING(f'\nFiltros disponíveis: {len(campos_filtro())}'))
