from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (
    DashboardView,
    profile_view,
    update_profile,
    update_avatar,
    remove_avatar,
    update_password,
    toggle_2fa,
    shipment_details,
    download_shipment_files,
    custom_404,
    register_view,
    custom_login_view,
    admin_panel,
    admin_create_user,
    admin_edit_user,
    admin_delete_user,
    admin_test_bot,
    admin_set_bot_access,
    admin_create_backup,
    admin_download_backup,
    admin_get_backup_info,
    admin_set_backup_interval,
    admin_clear_database,
    admin_restore_database,
    get_activity_logs,
)

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('register/', register_view, name='register'),
    path('login/', custom_login_view, name='login'),
    path('shipment/<str:shipment_id>/download/', download_shipment_files, name='download_shipment_files'),
    path('shipment/<str:shipment_id>/', shipment_details, name='shipment_details'),
    path('shipment/<str:shipment_id>/delete/', views.delete_shipment, name='delete_shipment'),
    path('profile/', profile_view, name='profile'),
    path('profile/update/', update_profile, name='update_profile'),
    path('profile/update-avatar/', update_avatar, name='update_avatar'),
    path('profile/remove-avatar/', remove_avatar, name='remove_avatar'),
    path('profile/update-password/', update_password, name='update_password'),
    path('accounts/register/', register_view, name='register'),
    path('accounts/login/', custom_login_view, name='login'),
    path('profile/toggle-2fa/', toggle_2fa, name='toggle_2fa'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('404/', custom_404, name='custom_404'),

    # Админ панель (с новым префиксом)
    path('system/', admin_panel, name='admin_panel'),

    # Управление пользователями
    path('system/create-user/', admin_create_user, name='admin_create_user'),
    path('system/edit-user/<int:user_id>/', admin_edit_user, name='admin_edit_user'),
    path('system/delete-user/<int:user_id>/', admin_delete_user, name='admin_delete_user'),

    # Управление ботом
    path('system/test-bot/', admin_test_bot, name='admin_test_bot'),
    path('system/set-bot-access/', admin_set_bot_access, name='admin_set_bot_access'),

    # Управление базой данных
    path('system/create-backup/', admin_create_backup, name='admin_create_backup'),
    path('system/download-backup/', admin_download_backup, name='admin_download_backup'),
    path('system/get-backup-info/', admin_get_backup_info, name='admin_get_backup_info'),
    path('system/set-backup-interval/', admin_set_backup_interval, name='admin_set_backup_interval'),
    path('system/clear-database/', admin_clear_database, name='admin_clear_database'),
    path('system/restore-database/', admin_restore_database, name='admin_restore_database'),
    path('system/get-activity-logs/', get_activity_logs, name='get_activity_logs'),
]

handler404 = 'core.views.custom_404'