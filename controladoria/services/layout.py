"""Contexto compartilhado do layout (sidebar, usuário)."""

CADASTROS_NAV_ITEMS = frozenset({
    'competencias',
    'contas_financeiras',
    'empresas',
    'socios',
})

REGRAS_NAV_ITEMS = frozenset({
    'dashboard',
    'medidas',
    'regras',
    'excecoes',
    'ajustes',
    'comissoes',
})

MOVIMENTOS_NAV_ITEMS = frozenset({
    'lancamentos',
    'imoveis_vendidos',
})


def get_layout_context(request) -> dict:
    return {
        'current_user': request.user,
    }


def apply_nav_sidebar_context(ctx: dict) -> dict:
    """Calcula expansão dos menus após nav_active estar no contexto."""
    nav_active = ctx.get('nav_active')
    ctx['nav_cadastros_expanded'] = nav_cadastros_expanded(nav_active)
    ctx['nav_regras_expanded'] = nav_regras_expanded(nav_active)
    ctx['nav_movimentos_expanded'] = nav_movimentos_expanded(nav_active)
    return ctx


def nav_cadastros_expanded(nav_active: str | None) -> bool:
    return bool(nav_active and nav_active in CADASTROS_NAV_ITEMS)


def nav_regras_expanded(nav_active: str | None) -> bool:
    return bool(nav_active and nav_active in REGRAS_NAV_ITEMS)


def nav_movimentos_expanded(nav_active: str | None) -> bool:
    return bool(nav_active and nav_active in MOVIMENTOS_NAV_ITEMS)
