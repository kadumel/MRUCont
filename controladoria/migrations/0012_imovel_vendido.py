# Generated manually for ImovelVendido

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('controladoria', '0011_conta_financeira_lancamento'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImovelVendido',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empreendimento_ajustado', models.CharField(blank=True, max_length=150)),
                ('cod_empreendimento', models.CharField(blank=True, max_length=20)),
                ('data_venda', models.DateField(blank=True, null=True)),
                ('contrato_ajustado', models.CharField(max_length=40, unique=True)),
                ('situacao', models.CharField(blank=True, max_length=40)),
                ('imovel', models.CharField(blank=True, max_length=200)),
                ('cliente', models.CharField(blank=True, max_length=200)),
                ('valor_tabela', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('desconto', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('valor_venda', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('valor_liquidado', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('situacao_contrato', models.CharField(blank=True, max_length=40)),
                ('data_rescisao_imobiliaria', models.DateField(blank=True, null=True)),
                ('imobiliaria', models.CharField(blank=True, max_length=150)),
                ('corretor', models.CharField(blank=True, max_length=150)),
                ('regra_comissao', models.CharField(blank=True, max_length=40)),
                ('comissao', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('regra_valor', models.CharField(blank=True, max_length=10)),
                ('competencia', models.DateField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Imóvel Vendido',
                'verbose_name_plural': 'Imóveis Vendidos',
                'ordering': ['-data_venda', 'contrato_ajustado'],
            },
        ),
    ]
