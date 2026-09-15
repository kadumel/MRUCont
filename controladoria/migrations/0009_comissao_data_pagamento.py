# Generated manually for comissao data_pagamento

from django.db import migrations, models


def copiar_data_pagamento(apps, schema_editor):
    Comissao = apps.get_model('controladoria', 'Comissao')
    for comissao in Comissao.objects.select_related('competencia').iterator():
        if comissao.competencia_id and comissao.competencia:
            comissao.data_pagamento = comissao.competencia.competencia
            comissao.save(update_fields=['data_pagamento'])


class Migration(migrations.Migration):

    dependencies = [
        ('controladoria', '0008_comissao'),
    ]

    operations = [
        migrations.AddField(
            model_name='comissao',
            name='data_pagamento',
            field=models.DateField(
                blank=True,
                help_text='Data prevista para pagamento da comissão.',
                null=True,
            ),
        ),
        migrations.RunPython(copiar_data_pagamento, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='comissao',
            name='competencia',
        ),
        migrations.AlterField(
            model_name='comissao',
            name='data_pagamento',
            field=models.DateField(help_text='Data prevista para pagamento da comissão.'),
        ),
    ]
