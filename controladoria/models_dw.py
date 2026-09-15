"""Modelos unmanaged das tabelas do Data Warehouse (somente leitura)."""

from django.conf import settings
from django.db import models


class FatoResultadoFinanceiroQ12(models.Model):
    """Legado — leitura direta da fato. Regras usam VW_Q12_SISTEMA via consulta_base."""

    Q = models.CharField(max_length=3, db_column='Q', null=True, blank=True)
    Data = models.DateTimeField(db_column='Data', null=True, blank=True)
    cdEmpresa = models.CharField(max_length=10, db_column='cdEmpresa', null=True, blank=True)
    cdNucleo = models.CharField(max_length=3, db_column='cdNucleo', null=True, blank=True)
    cdCentro = models.CharField(max_length=15, db_column='cdCentro', null=True, blank=True)
    cdGrupoCentro = models.CharField(max_length=3, db_column='cdGrupoCentro', null=True, blank=True)
    Origem = models.CharField(max_length=15, db_column='Origem', null=True, blank=True)
    RDZ = models.CharField(max_length=3, db_column='RDZ', null=True, blank=True)
    DC = models.CharField(max_length=10, db_column='DC', null=True, blank=True)
    Parcela = models.CharField(max_length=10, db_column='Parcela', null=True, blank=True)
    valor = models.FloatField(db_column='valor', null=True, blank=True)
    chaveOrc = models.TextField(db_column='chaveOrc', null=True, blank=True)
    Assunto = models.CharField(max_length=150, db_column='Assunto', null=True, blank=True)
    Classificacao = models.CharField(max_length=150, db_column='Classificacao', null=True, blank=True)
    ClienteFornecedor = models.CharField(max_length=150, db_column='ClienteFornecedor', null=True, blank=True)
    tipo = models.CharField(max_length=9, db_column='tipo', null=True, blank=True)
    cdEmpreendimento = models.CharField(max_length=11, db_column='cdEmpreendimento', null=True, blank=True)
    cdSubGrupo = models.CharField(max_length=18, db_column='cdSubGrupo', null=True, blank=True)
    nmSubGrupo = models.CharField(max_length=150, db_column='nmSubGrupo', null=True, blank=True)
    Segmento = models.CharField(max_length=10, db_column='Segmento', null=True, blank=True)
    siban = models.CharField(max_length=50, db_column='siban', null=True, blank=True)
    observacaoDoc = models.TextField(db_column='observacaoDoc', null=True, blank=True)

    class Meta:
        managed = False
        app_label = 'controladoria_dw'
        db_table = f'[{settings.DATABASE_SCHEMA_DW}].[{settings.FONTE_REGRAS_TABELA}]'


class DimSubGrupo(models.Model):
    cdSubGrupo = models.CharField(max_length=18, db_column='cdSubGrupo', primary_key=True)
    nmSubGrupo = models.CharField(max_length=150, db_column='nmSubGrupo', null=True, blank=True)

    class Meta:
        managed = False
        app_label = 'controladoria_dw'
        db_table = f'[{settings.DATABASE_SCHEMA_DW}].[DimSubGrupo]'
