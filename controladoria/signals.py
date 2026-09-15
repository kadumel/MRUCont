"""Sincroniza exceções, ajustes e view de regras com o DW."""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from controladoria.models import AjusteManual, ExcecaoLancamento, Medida, RegraMedida
from controladoria.services.ajuste_dw import AjusteDWError, remover_ajuste_dw
from controladoria.services.excecao_dw import ExcecaoDWError, remover_excecao_dw
from controladoria.services.motor_regras import MotorRegrasError
from controladoria.services.view_regras_dw import ViewRegrasDWError, atualizar_view_regras_dw

logger = logging.getLogger(__name__)


def _agendar_atualizacao_view_regras() -> None:
    def _sync():
        try:
            atualizar_view_regras_dw()
        except ViewRegrasDWError as err:
            logger.warning('Falha ao atualizar view de regras no DW: %s', err)

    transaction.on_commit(_sync)


@receiver(post_save, sender=Medida)
@receiver(post_save, sender=RegraMedida)
@receiver(post_delete, sender=Medida)
@receiver(post_delete, sender=RegraMedida)
def sync_view_regras_sistema(sender, **kwargs):
    _agendar_atualizacao_view_regras()


@receiver(pre_delete, sender=ExcecaoLancamento)
def sync_excecao_remocao_dw(sender, instance, **kwargs):
    try:
        remover_excecao_dw(instance)
    except ExcecaoDWError as err:
        raise MotorRegrasError(str(err)) from err


@receiver(pre_delete, sender=AjusteManual)
def sync_ajuste_remocao_dw(sender, instance, **kwargs):
    try:
        remover_ajuste_dw(instance)
    except AjusteDWError as err:
        raise MotorRegrasError(str(err)) from err
