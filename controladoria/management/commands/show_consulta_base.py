"""Exibe a consulta base das regras e os campos configurados."""

from django.core.management.base import BaseCommand

from controladoria.services.consulta_base import (
    campos_agregacao,
    campos_filtro,
    fato_sql,
    get_campos_consulta,
    origem_campos_consulta,
    sql_consulta_base_preview,
    usa_joins_dim,
)


class Command(BaseCommand):
    help = 'Mostra a consulta base das regras e os campos configurados.'

    def handle(self, *args, **options):
        campos = get_campos_consulta()
        self.stdout.write(self.style.MIGRATE_HEADING('Consulta base — configuração'))
        self.stdout.write(f'Fonte DW: {fato_sql()}')
        self.stdout.write(f'Origem colunas: {origem_campos_consulta()}')
        self.stdout.write(f'Joins dimensão: {"sim" if usa_joins_dim() else "não (colunas na VIEW)"}')
        self.stdout.write(self.style.MIGRATE_HEADING('\nCampos carregados'))
        self.stdout.write(f'Total: {len(campos)}')

        self.stdout.write(f'\nFiltros ({len(campos_filtro())}):')
        for campo_id, label in campos_filtro():
            self.stdout.write(f'  - {campo_id}: {label}')

        self.stdout.write(f'\nAgregação ({len(campos_agregacao())}):')
        for campo_id, label in campos_agregacao():
            self.stdout.write(f'  - {campo_id}: {label}')

        self.stdout.write(self.style.MIGRATE_HEADING('\nPrévia SQL'))
        self.stdout.write(sql_consulta_base_preview())
        self.stdout.write(
            self.style.WARNING(
                '\nColunas vêm da VIEW automaticamente. Após alterar a VIEW: '
                'python manage.py sync_campos_view'
            )
        )
