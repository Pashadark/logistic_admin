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

    // Обработчик для кнопки отправки в группу
    const sendToGroupBtn = document.getElementById('sendToGroupBtn');
    if (sendToGroupBtn) {
        sendToGroupBtn.addEventListener('click', function() {
            const messageText = document.getElementById('botMessageText').value;
            const originalText = sendToGroupBtn.innerHTML;

            // Показываем индикатор загрузки
            sendToGroupBtn.disabled = true;
            sendToGroupBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Отправка...';

            fetch('/system/test-bot/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                },
                body: JSON.stringify({
                    message: messageText,
                    is_group_message: true
                })
            })
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    showToast(data.message, 'success');

                    // Обновляем блок с результатом (если он есть)
                    const resultDiv = document.getElementById('botTestResult');
                    if (resultDiv) {
                        resultDiv.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
                    }
                } else {
                    showToast(data.message || 'Произошла ошибка', 'error');
                }
            })
            .catch(error => {
                showToast('Ошибка сети: ' + error.message, 'error');
                console.error('Error:', error);
            })
            .finally(() => {
                sendToGroupBtn.disabled = false;
                sendToGroupBtn.innerHTML = originalText;
            });
        });
    }

    // Функция для получения CSRF токена
    function getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }

    // Запускаем обработку сообщений при загрузке
    processDjangoMessages();
});