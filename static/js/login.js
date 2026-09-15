document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('password-toggle');
    const input = document.getElementById('id_password');
    if (!toggle || !input) return;

    toggle.addEventListener('click', () => {
        const visible = input.type === 'text';
        input.type = visible ? 'password' : 'text';
        const label = toggle.querySelector('.password-field__label');
        if (label) label.textContent = visible ? 'Mostrar' : 'Ocultar';
    });
});
