from django.urls import path
from .views import DashboardView
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('profile/update-avatar/', views.update_avatar, name='update_avatar'),
    path('profile/remove-avatar/', views.remove_avatar, name='remove_avatar'),
    path('profile/update-password/', views.update_password, name='update_password'),
    path('profile/toggle-2fa/', views.toggle_2fa, name='toggle_2fa'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
]
