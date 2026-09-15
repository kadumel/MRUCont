from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

from controladoria.services.layout import apply_nav_sidebar_context, get_layout_context


class ControladoriaLayoutMixin(LoginRequiredMixin):
    login_url = reverse_lazy('controladoria:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_layout_context(self.request))
        return ctx

    def render_to_response(self, context, **response_kwargs):
        apply_nav_sidebar_context(context)
        return super().render_to_response(context, **response_kwargs)

    def build_layout_context(self, **extra):
        """Monta contexto de página para views que usam render() direto."""
        ctx = {**get_layout_context(self.request), **extra}
        return apply_nav_sidebar_context(ctx)
