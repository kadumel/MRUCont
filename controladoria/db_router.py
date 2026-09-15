"""Roteador: modelos unmanaged do DW usam conexão 'dw'."""


class DWRouter:
    dw_app_labels = {'controladoria_dw'}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.dw_app_labels:
            return 'dw'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.dw_app_labels:
            return 'dw'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.dw_app_labels:
            return False
        if db == 'dw':
            return False
        return None
