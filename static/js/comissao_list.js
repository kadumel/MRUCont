(function () {
    function setupTabs() {
        const tabs = document.querySelectorAll('.js-comissao-tab');
        const panels = document.querySelectorAll('.js-comissao-panel');
        if (!tabs.length || !panels.length) return;

        function activateTab(tabName) {
            tabs.forEach((tab) => {
                const isActive = tab.dataset.tab === tabName;
                tab.classList.toggle('tabs-nav__item--active', isActive);
                if (isActive) {
                    tab.setAttribute('aria-current', 'page');
                } else {
                    tab.removeAttribute('aria-current');
                }
            });

            panels.forEach((panel) => {
                panel.hidden = panel.dataset.tab !== tabName;
            });
        }

        tabs.forEach((tab) => {
            tab.addEventListener('click', (event) => {
                event.preventDefault();
                const tabName = tab.dataset.tab;
                if (!tabName) return;
                activateTab(tabName);
                const url = tab.getAttribute('href');
                if (url) {
                    window.history.replaceState(null, '', url);
                }
            });
        });
    }

    function setupModal(modalId, options) {
        const modal = document.getElementById(modalId);
        if (!modal) return null;

        function setModalOpen(isOpen) {
            modal.hidden = !isOpen;
            modal.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
            if (isOpen) {
                modal.removeAttribute('inert');
                document.body.classList.add('modal-open');
            } else {
                modal.setAttribute('inert', '');
                if (!document.querySelector('.modal:not([hidden])')) {
                    document.body.classList.remove('modal-open');
                }
            }
        }

        function openModal() {
            setModalOpen(true);
            if (options.onOpen) options.onOpen(modal);
        }

        function closeModal() {
            setModalOpen(false);
        }

        setModalOpen(false);

        modal.querySelectorAll('[data-modal-close]').forEach((el) => {
            el.addEventListener('click', closeModal);
        });

        return { openModal, closeModal, modal };
    }

    setupTabs();

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        const openModal = document.querySelector('.modal:not([hidden])');
        if (!openModal) return;
        openModal.hidden = true;
        openModal.setAttribute('aria-hidden', 'true');
        openModal.setAttribute('inert', '');
        if (!document.querySelector('.modal:not([hidden])')) {
            document.body.classList.remove('modal-open');
        }
    });

    const incluirModal = setupModal('modal-comissao', {
        onOpen(modal) {
            const input = modal.querySelector('#data_pagamento');
            if (input) input.focus();
        },
    });

    if (incluirModal) {
        const contratoLabel = document.getElementById('modal-contrato-label');
        const clienteLabel = document.getElementById('modal-cliente-label');
        const dataPagamentoInput = document.getElementById('data_pagamento');

        const fieldMap = {
            cd_contrato: 'field-cd-contrato',
            data_contrato: 'field-data-contrato',
            cd_empresa: 'field-cd-empresa',
            contrato: 'field-contrato',
            situacao: 'field-situacao',
            cd_cliente: 'field-cd-cliente',
            cliente: 'field-cliente',
            valor_tabela_primeira: 'field-valor-tabela-primeira',
            valor_tabela_venda: 'field-valor-tabela-venda',
            valor_venda_a_vista: 'field-valor-venda-a-vista',
            desconto: 'field-desconto',
            liquidado: 'field-liquidado',
            percentual: 'field-percentual',
            comissao: 'field-comissao',
        };

        document.querySelectorAll('.js-incluir-comissao').forEach((button) => {
            button.addEventListener('click', () => {
                const dataset = button.dataset;
                Object.entries(fieldMap).forEach(([dataKey, fieldId]) => {
                    const camelKey = dataKey.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
                    const field = document.getElementById(fieldId);
                    if (field) field.value = dataset[camelKey] || '';
                });
                if (contratoLabel) contratoLabel.textContent = dataset.cdContrato || 'Contrato';
                if (clienteLabel) clienteLabel.textContent = dataset.cliente || '';
                if (dataPagamentoInput) dataPagamentoInput.value = '';
                incluirModal.openModal();
            });
        });
    }

    const editarModal = setupModal('modal-editar-comissao', {
        onOpen(modal) {
            const input = modal.querySelector('#editar_data_pagamento');
            if (input) input.focus();
        },
    });

    if (editarModal) {
        const formEditar = document.getElementById('form-editar-comissao');
        const contratoLabel = document.getElementById('modal-editar-contrato-label');
        const clienteLabel = document.getElementById('modal-editar-cliente-label');
        const dataPagamentoInput = document.getElementById('editar_data_pagamento');

        document.querySelectorAll('.js-editar-comissao').forEach((button) => {
            button.addEventListener('click', () => {
                const dataset = button.dataset;
                if (formEditar) formEditar.action = dataset.actionUrl || '';
                if (contratoLabel) contratoLabel.textContent = dataset.cdContrato || 'Contrato';
                if (clienteLabel) clienteLabel.textContent = dataset.cliente || '';
                if (dataPagamentoInput) dataPagamentoInput.value = dataset.dataPagamento || '';
                editarModal.openModal();
            });
        });
    }

    const excluirModal = setupModal('modal-excluir-comissao');

    if (excluirModal) {
        const formExcluir = document.getElementById('form-excluir-comissao');
        const contratoLabel = document.getElementById('modal-excluir-contrato-label');

        document.querySelectorAll('.js-excluir-comissao').forEach((button) => {
            button.addEventListener('click', () => {
                const dataset = button.dataset;
                if (formExcluir) formExcluir.action = dataset.actionUrl || '';
                if (contratoLabel) contratoLabel.textContent = dataset.cdContrato || '';
                excluirModal.openModal();
            });
        });
    }
})();
