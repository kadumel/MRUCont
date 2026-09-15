from django.core.management.base import BaseCommand

from controladoria.services.excecao_dw import ExcecaoDWError, sincronizar_todas_excecoes_dw


class Command(BaseCommand):
    help = 'Sincroniza exceções do app (SQLite) para [FatoExcecaoLancamento] no DW.'

    def handle(self, *args, **options):
        try:
            inseridas, erros = sincronizar_todas_excecoes_dw()
        except ExcecaoDWError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Sincronização concluída: {inseridas} exceção(ões) enviada(s) ao DW.'
        ))
        if erros:
            self.stdout.write(self.style.WARNING(f'{erros} registro(s) com erro.'))
