from django.core.management.base import BaseCommand

from controladoria.services.ajuste_dw import AjusteDWError, criar_tabela_ajuste_dw


class Command(BaseCommand):
    help = 'Cria a tabela [FatoAjusteLancamento] no DW, se ainda não existir.'

    def handle(self, *args, **options):
        try:
            criar_tabela_ajuste_dw()
        except AjusteDWError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            'Tabela [FatoAjusteLancamento] verificada/criada no DW.'
        ))
