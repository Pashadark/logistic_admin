// Обработчик для сброса фильтров
document.getElementById('resetFilters').addEventListener('click', function() {
    document.getElementById('searchInput').value = '';
    document.getElementById('statusFilter').value = '';
    document.getElementById('typeFilter').value = '';
    document.getElementById('shipmentFilterForm').submit();
});

// Инициализация tooltips
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Обработчик для обновления статуса отправки
    document.querySelectorAll('.status-update-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const shipmentId = this.dataset.shipmentId;
            const newStatus = this.dataset.status;

            fetch(`/shipments/${shipmentId}/update_status/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({status: newStatus})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert('success', data.message);
                    // Обновляем строку таблицы
                    const row = document.querySelector(`tr[data-shipment-id="${shipmentId}"]`);
                    if (row) {
                        const statusBadge = row.querySelector('.status-badge');
                        if (statusBadge) {
                            statusBadge.className = `badge badge-${newStatus}`;
                            statusBadge.textContent = data.new_status_display;
                        }
                    }
                } else {
                    showAlert('danger', data.message);
                }
            })
            .catch(error => {
                showAlert('danger', 'Ошибка при обновлении статуса');
            });
        });
    });
});

// Функция для получения CSRF токена
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}