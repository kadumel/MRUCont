(function () {
    const container = document.getElementById('socio-empresa-rows');
    const addBtn = document.getElementById('add-socio-empresa');
    const emptyTpl = document.getElementById('socio-empresa-empty');
    const totalInput = document.getElementById('id_empresas-TOTAL_FORMS');

    if (!container || !addBtn || !emptyTpl || !totalInput) {
        return;
    }

    addBtn.addEventListener('click', function () {
        const index = parseInt(totalInput.value, 10);
        const html = emptyTpl.innerHTML.replace(/__prefix__/g, String(index));
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        const row = wrapper.firstElementChild;
        if (row) {
            container.appendChild(row);
        }
        totalInput.value = String(index + 1);
    });
})();
