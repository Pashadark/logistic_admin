document.addEventListener('DOMContentLoaded', function() {
    // Проверка загрузки SweetAlert2
    if (typeof Swal === 'undefined') {
        console.error('SweetAlert2 не загружен!');
        return;
    }

    // Функция для отображения уведомления
    function showToast(message, type) {
        const Toast = Swal.mixin({
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 3000,
            timerProgressBar: true,
            didOpen: (toast) => {
                toast.addEventListener('mouseenter', Swal.stopTimer);
                toast.addEventListener('mouseleave', Swal.resumeTimer);
            }
        });

        const typeSettings = {
            'success': {icon: 'success', color: '#28a745'},
            'error': {icon: 'error', color: '#dc3545'},
            'warning': {icon: 'warning', color: '#ffc107'},
            'info': {icon: 'info', color: '#17a2b8'},
            'debug': {icon: 'question', color: '#6c757d'}
        };

        const settings = typeSettings[type] || typeSettings['info'];

        Toast.fire({
            icon: settings.icon,
            title: message,
            iconColor: settings.color
        });
    }

    // Проверка наличия сообщений Django
    const messageElements = document.querySelectorAll('[data-django-message]');
    if (messageElements.length > 0) {
        messageElements.forEach(el => {
            showToast(el.textContent, el.dataset.messageType);
        });
    }
});