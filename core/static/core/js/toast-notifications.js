document.addEventListener('DOMContentLoaded', function() {
    // Проверка загрузки SweetAlert2
    if (typeof Swal === 'undefined') {
        console.error('SweetAlert2 не загружен!');
        return;
    }

    // Настройки для разных типов сообщений
    const toastSettings = {
        success: {
            icon: 'success',
            iconColor: '#28a745',
            background: '#f8f9fa',
            color: '#212529'
        },
        error: {
            icon: 'error',
            iconColor: '#dc3545',
            background: '#f8f9fa',
            color: '#212529'
        },
        warning: {
            icon: 'warning',
            iconColor: '#ffc107',
            background: '#f8f9fa',
            color: '#212529'
        },
        info: {
            icon: 'info',
            iconColor: '#17a2b8',
            background: '#f8f9fa',
            color: '#212529'
        },
        debug: {
            icon: 'question',
            iconColor: '#6c757d',
            background: '#f8f9fa',
            color: '#212529'
        }
    };

    // Функция для отображения уведомления
    function showToast(message, type = 'info') {
        const settings = toastSettings[type] || toastSettings.info;

        const Toast = Swal.mixin({
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 3000,
            timerProgressBar: true,
            background: settings.background,
            color: settings.color,
            didOpen: (toast) => {
                toast.addEventListener('mouseenter', Swal.stopTimer);
                toast.addEventListener('mouseleave', Swal.resumeTimer);
            }
        });

        Toast.fire({
            icon: settings.icon,
            title: message,
            iconColor: settings.iconColor
        });
    }

    // Обработка сообщений Django
    function processDjangoMessages() {
        const messageElements = document.querySelectorAll('[data-django-message]');

        messageElements.forEach(el => {
            const message = el.textContent.trim();
            const type = el.dataset.messageType || 'info';

            // Маппинг тегов Django на наши типы
            const typeMapping = {
                'success': 'success',
                'error': 'error',
                'warning': 'warning',
                'info': 'info',
                'debug': 'debug'
            };

            const finalType = typeMapping[type] || 'info';
            showToast(message, finalType);

            // Удаляем элемент после показа
            el.remove();
        });
    }

    // Запускаем обработку сообщений при загрузке
    processDjangoMessages();
});