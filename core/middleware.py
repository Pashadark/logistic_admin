from django.utils import timezone
from django.contrib.auth import logout
from django.contrib.auth.models import AnonymousUser
from .models import UserActivity
from django.utils.deprecation import MiddlewareMixin

class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if 'last_activity' in request.session:
                last_activity = request.session['last_activity']
                idle_time = timezone.now() - last_activity
                if idle_time.total_seconds() > settings.SESSION_COOKIE_AGE:
                    # Логируем завершение сессии по таймауту
                    UserActivity.objects.create(
                        user=request.user,
                        action_type='SESSION_END',
                        description='Сессия завершена по таймауту'
                    )
                    logout(request)
                    request.user = AnonymousUser()

            request.session['last_activity'] = timezone.now()

        response = self.get_response(request)
        return response

class UpdateLastActivityMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            # Обновляем время последней активности
            profile = request.user.profile
            profile.last_activity = timezone.now()
            profile.save()
        return None