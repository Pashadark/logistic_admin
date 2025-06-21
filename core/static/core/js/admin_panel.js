// Конфигурация
const config = {
    apiUrls: {
        activityLogs: '/admin/get-activity-logs/'
    },
    actionIcons: {
        'LOGIN': 'bi-box-arrow-in-right',
        'LOGOUT': 'bi-box-arrow-right',
        'PROFILE_UPDATE': 'bi-person-lines-fill',
        'PASSWORD_CHANGE': 'bi-shield-lock',
        'BOT_TEST': 'bi-robot',
        'SHIPMENT_CREATE': 'bi-plus-square',
        'SHIPMENT_UPDATE': 'bi-pencil-square',
        'SHIPMENT_DELETE': 'bi-trash',
        'BACKUP_CREATE': 'bi-save',
        'DEFAULT': 'bi-activity'
    }
};

// Получение CSRF токена
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// Загрузка логов
async function loadActivityLogs() {
    const logsTableBody = document.getElementById('logsTableBody');
    if (!logsTableBody) return;

    // Показываем индикатор загрузки
    showLoadingIndicator(logsTableBody);

    try {
        const response = await fetch(config.apiUrls.activityLogs, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.status === 'success') {
            renderLogsTable(data.logs);
        } else {
            throw new Error(data.message || 'Неизвестная ошибка сервера');
        }
    } catch (error) {
        console.error('Ошибка загрузки логов:', error);
        showError(logsTableBody, error.message);
    }
}

// Показать индикатор загрузки
function showLoadingIndicator(container) {
    container.innerHTML = `
        <tr>
            <td colspan="4" class="text-center py-4">
                <div class="spinner-border spinner-border-sm text-primary" role="status">
                    <span class="visually-hidden">Загрузка...</span>
                </div>
                <span class="ms-2">Загрузка логов...</span>
            </td>
        </tr>
    `;
}

// Показать ошибку
function showError(container, message) {
    container.innerHTML = `
        <tr>
            <td colspan="4" class="text-center py-4">
                <div class="alert alert-danger m-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    ${message || 'Произошла ошибка при загрузке'}
                </div>
            </td>
        </tr>
    `;
}

// Отрисовка таблицы логов
function renderLogsTable(logs) {
    const logsTableBody = document.getElementById('logsTableBody');

    if (!logs || logs.length === 0) {
        logsTableBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center py-4 text-muted">
                    <i class="bi bi-info-circle"></i> Нет данных для отображения
                </td>
            </tr>
        `;
        return;
    }

    logsTableBody.innerHTML = logs.map(log => `
        <tr>
            <td class="align-middle">
                <small class="text-muted">${log.timestamp}</small>
            </td>
            <td class="align-middle">
                <span class="fw-semibold">${log.user}</span>
            </td>
            <td class="align-middle">
                <i class="bi ${config.actionIcons[log.action_type] || config.actionIcons.DEFAULT} me-2"></i>
                ${log.action}
            </td>
            <td class="align-middle">${log.description}</td>
        </tr>
    `).join('');
}

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    // Загрузка логов при открытии вкладки
    const logsTab = document.getElementById('logs-tab');
    if (logsTab) {
        logsTab.addEventListener('click', loadActivityLogs);
    }

    // Кнопка обновления
    const refreshBtn = document.getElementById('refreshLogsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadActivityLogs);
    }
});