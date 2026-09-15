from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Cria usuário para acesso ao portal (não-admin).'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='controladoria')
        parser.add_argument('--password', default='controladoria123')
        parser.add_argument('--email', default='controladoria@local')

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        password = options['password']
        email = options['email']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': False, 'is_superuser': False},
        )
        user.set_password(password)
        user.is_active = True
        user.save()

        acao = 'criado' if created else 'atualizado'
        self.stdout.write(self.style.SUCCESS(
            f'Usuário "{username}" {acao}. Acesse http://127.0.0.1:8000/login/'
        ))
