from django.core.management.base import BaseCommand

from controladoria.services.view_regras_dw import ViewRegrasDWError, atualizar_view_regras_dw


class Command(BaseCommand):
    help = 'Cria ou atualiza a view [VW_REGRAS_SISTEMA] no DW com o SQL consolidado das regras.'

    def handle(self, *args, **options):
        try:
            view = atualizar_view_regras_dw()
        except ViewRegrasDWError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(f'View atualizada: {view}'))
