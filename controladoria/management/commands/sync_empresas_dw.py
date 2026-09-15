from django.core.management.base import BaseCommand

from controladoria.services.empresa_dw import EmpresaDWError, sincronizar_todas_empresas_dw


class Command(BaseCommand):
    help = 'Sincroniza empresas do app (SQLite) para [DimEmpresa] no DW.'

    def handle(self, *args, **options):
        try:
            sincronizadas, erros = sincronizar_todas_empresas_dw()
        except EmpresaDWError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Sincronização concluída: {sincronizadas} empresa(s) enviada(s) ao DW.'
        ))
        if erros:
            self.stdout.write(self.style.WARNING(f'{erros} registro(s) com erro.'))
