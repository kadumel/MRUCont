document.addEventListener('DOMContentLoaded', () => {
    const filtroLinhaTemplate = document.getElementById('filtro-linha-template');
    const grupoTemplate = document.getElementById('filtro-grupo-template');

    function rotuloOperadorRaiz(operador) {
        return operador === 'and' ? 'E' : 'OU';
    }

    function getOperadorRaiz(container) {
        const secao = container.dataset.gruposSecao;
        const select = container.closest('.filtro-secao')?.querySelector(`[name="${secao}_operador_raiz"]`);
        return select?.value === 'and' ? 'and' : 'or';
    }

    function atualizarOperadorRaizUI(container) {
        const secaoEl = container.closest('.filtro-secao');
        const operador = getOperadorRaiz(container);
        const rotulo = rotuloOperadorRaiz(operador);
        const grupos = container.querySelectorAll('.filtro-grupo');

        container.querySelectorAll('.filtro-grupo-sep').forEach((sep) => {
            sep.textContent = rotulo;
        });

        const btnAdd = secaoEl?.querySelector('.btn-add-grupo');
        if (btnAdd) {
            btnAdd.textContent = grupos.length >= 1
                ? `+ Adicionar grupo (${rotulo})`
                : '+ Adicionar grupo';
        }

        const operadorField = secaoEl?.querySelector('.field--operador-raiz');
        if (operadorField) {
            operadorField.hidden = grupos.length < 2;
        }
    }

    function atualizarIndicesGrupos(container, secao) {
        const grupos = container.querySelectorAll('.filtro-grupo');
        grupos.forEach((grupo, index) => {
            grupo.dataset.grupoIndex = String(index);
            const titulo = grupo.querySelector('.filtro-grupo__header strong');
            if (titulo) titulo.textContent = `Grupo ${index + 1}`;

            grupo.querySelectorAll('[name]').forEach((el) => {
                el.name = el.name.replace(new RegExp(`${secao}_grupo_\\d+_`), `${secao}_grupo_${index}_`);
            });
        });

        const countInput = container.closest('.filtro-secao')?.querySelector('.grupo-count-input');
        if (countInput) countInput.value = String(grupos.length);

        const rotulo = rotuloOperadorRaiz(getOperadorRaiz(container));
        container.querySelectorAll('.filtro-grupo-sep').forEach((sep) => sep.remove());
        container.querySelectorAll('.filtro-secao__vazio').forEach((msg) => msg.remove());
        grupos.forEach((grupo, index) => {
            if (index === 0) return;
            const sep = document.createElement('div');
            sep.className = 'filtro-grupo-sep';
            sep.textContent = rotulo;
            container.insertBefore(sep, grupo);
        });

        atualizarOperadorRaizUI(container);
    }

    function bindRemoveFiltro(builder) {
        builder.querySelectorAll('.btn-remover-filtro').forEach((btn) => {
            btn.onclick = () => {
                const linhas = builder.querySelectorAll('.filtro-linha');
                if (linhas.length <= 1) {
                    linhas[0].querySelector('[name$="_valores"]').value = '';
                    return;
                }
                btn.closest('.filtro-linha').remove();
            };
        });
    }

    function bindAddFiltro(grupo, secao) {
        const btn = grupo.querySelector('.btn-add-filtro');
        const builder = grupo.querySelector('.filtros-builder');
        if (!btn || !builder || !filtroLinhaTemplate) return;

        btn.onclick = () => {
            const index = grupo.dataset.grupoIndex || '0';
            const html = filtroLinhaTemplate.innerHTML
                .replaceAll('__SECAO__', secao)
                .replaceAll('__GRUPO__', index);
            builder.insertAdjacentHTML('beforeend', html);
            bindRemoveFiltro(builder);
        };
    }

    function bindRemoveGrupo(grupo, container, secao) {
        const btn = grupo.querySelector('.btn-remover-grupo');
        if (!btn) return;
        btn.onclick = () => {
            grupo.remove();
            atualizarIndicesGrupos(container, secao);
        };
    }

    function initGrupo(grupo, container, secao) {
        bindAddFiltro(grupo, secao);
        bindRemoveGrupo(grupo, container, secao);
        const builder = grupo.querySelector('.filtros-builder');
        if (builder) bindRemoveFiltro(builder);
    }

    function initSecao(secaoContainer) {
        const secao = secaoContainer.dataset.gruposSecao;
        if (!secao) return;

        secaoContainer.querySelectorAll('.filtro-grupo').forEach((grupo) => {
            initGrupo(grupo, secaoContainer, secao);
        });
        atualizarIndicesGrupos(secaoContainer, secao);

        secaoContainer.closest('.filtro-secao')
            ?.querySelector('.operador-raiz-select')
            ?.addEventListener('change', () => {
                atualizarIndicesGrupos(secaoContainer, secao);
            });

        secaoContainer.closest('.filtro-secao')
            ?.querySelector('.btn-add-grupo')
            ?.addEventListener('click', () => {
                if (!grupoTemplate || !filtroLinhaTemplate) return;

                secaoContainer.querySelector('.filtro-secao__vazio')?.remove();

                const index = secaoContainer.querySelectorAll('.filtro-grupo').length;
                const num = index + 1;
                let html = grupoTemplate.innerHTML
                    .replaceAll('__SECAO__', secao)
                    .replaceAll('__GRUPO__', String(index))
                    .replaceAll('__NUM__', String(num));
                secaoContainer.insertAdjacentHTML('beforeend', html);

                const novoGrupo = secaoContainer.querySelector(`.filtro-grupo[data-grupo-index="${index}"]`);
                if (novoGrupo) {
                    const builder = novoGrupo.querySelector('.filtros-builder');
                    const linhaHtml = filtroLinhaTemplate.innerHTML
                        .replaceAll('__SECAO__', secao)
                        .replaceAll('__GRUPO__', String(index));
                    builder.insertAdjacentHTML('beforeend', linhaHtml);
                    initGrupo(novoGrupo, secaoContainer, secao);
                }
                atualizarIndicesGrupos(secaoContainer, secao);
            });
    }

    document.querySelectorAll('[data-grupos-secao]').forEach(initSecao);
});
