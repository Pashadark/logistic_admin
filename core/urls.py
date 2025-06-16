from django.urls import path
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
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('shipment/<str:shipment_id>/', shipment_details, name='shipment_details'),  # Изменили на <str:shipment_id>
    path('profile/', profile_view, name='profile'),
    path('profile/update/', update_profile, name='update_profile'),
    path('profile/update-avatar/', update_avatar, name='update_avatar'),
    path('profile/remove-avatar/', remove_avatar, name='remove_avatar'),
    path('profile/update-password/', update_password, name='update_password'),
    path('profile/toggle-2fa/', toggle_2fa, name='toggle_2fa'),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('404/', custom_404, name='custom_404'),
]

handler404 = 'core.views.custom_404'