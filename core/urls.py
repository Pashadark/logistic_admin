from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import download_shipment_files
from django.contrib.auth import views as auth_views
from .views import shipment_details
from .views import register_view, custom_login_view
from . import views
from .views import (
    DashboardView,
    shipment_details,
    profile_view,
    update_profile,
    update_avatar,
    remove_avatar,
    update_password,
    toggle_2fa,
    CustomLoginView,
    update_shipment_status,
    create_shipment,
    delete_shipment,
    custom_404
)


urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
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
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('404/', custom_404, name='custom_404'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'core.views.custom_404'