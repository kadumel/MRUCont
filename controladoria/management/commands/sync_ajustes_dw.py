from django.core.management.base import BaseCommand

from controladoria.services.ajuste_dw import (
    AjusteDWError,
    criar_tabela_ajuste_dw,
    sincronizar_todos_ajustes_dw,
)


class Command(BaseCommand):
    help = 'Sincroniza ajustes do app (SQLite) para [FatoAjusteLancamento] no DW.'

    def handle(self, *args, **options):
        try:
            criar_tabela_ajuste_dw()
            inseridas, erros = sincronizar_todos_ajustes_dw()
        except AjusteDWError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Sincronização concluída: {inseridas} ajuste(s) enviado(s) ao DW.'
        ))
        if erros:
            self.stdout.write(self.style.WARNING(f'{erros} registro(s) com erro.'))
