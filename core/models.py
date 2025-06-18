from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.views.generic import TemplateView
from django.core.paginator import Paginator
from cargo_admin.models import Shipment
from django.db.models import Q
from django.views import View
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    telegram_id = models.CharField(max_length=100, blank=True, null=True)
    two_factor_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile of {self.user.username}'

    @property
    def full_name(self):
        return f'{self.user.first_name} {self.user.last_name}'.strip()

    @property
    def telegram_username(self):
        return self.telegram_id if self.telegram_id else None


class Shipment(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создано'),
        ('processing', 'В обработке'),
        ('transit', 'В пути'),
        ('delivered', 'Доставлено'),
        ('problem', 'Проблема'),
    ]

    TYPE_CHOICES = [
        ('send', 'Отправка'),
        ('receive', 'Получение'),
    ]

    id = models.CharField(max_length=20, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    waybill_photo = models.ImageField(upload_to='waybills/', blank=True, null=True)
    product_photo = models.ImageField(upload_to='products/', blank=True, null=True)
    waybill_number = models.CharField(max_length=50)
    city = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    comment = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Новые поля для хранения Telegram file_id
    telegram_waybill_file_id = models.CharField(max_length=255, blank=True, null=True)
    telegram_product_file_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Отправление #{self.id}"

    def get_status_display(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    def clean(self):
        super().clean()
        errors = {}

        # Проверка номера накладной
        if not self.waybill_number:
            errors['waybill_number'] = 'Номер накладной обязателен'

        # Проверка города
        if not self.city:
            errors['city'] = 'Город обязателен'

        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()  # Вызывает clean() перед сохранением
        super().save(*args, **kwargs)

class UserActivity(models.Model):
    ACTION_CHOICES = [
        ('LOGIN', 'Вход в систему'),
        ('LOGOUT', 'Выход из системы'),
        ('PROFILE_UPDATE', 'Обновление профиля'),
        ('PASSWORD_CHANGE', 'Смена пароля'),
        ('AVATAR_CHANGE', 'Смена аватара'),
        ('SHIPMENT_CREATE', 'Создание отправки'),
        ('SHIPMENT_UPDATE', 'Обновление отправки'),
        ('SHIPMENT_DELETE', 'Удаление отправки'),
        ('SHIPMENT_STATUS', 'Изменение статуса отправки'),
        ('SHIPMENT_VIEW', 'Просмотр отправки'),
        ('2FA_TOGGLE', 'Изменение 2FA'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user.username} - {self.get_action_type_display()} at {self.timestamp}'

    @classmethod
    def log_activity(cls, user, action_type, description='', metadata=None):
        return cls.objects.create(
            user=user,
            action_type=action_type,
            description=description,
            metadata=metadata or {}
        )

    @property
    def color(self):
        color_map = {
            'LOGIN': 'success',
            'LOGOUT': 'secondary',
            'PROFILE_UPDATE': 'primary',
            'PASSWORD_CHANGE': 'warning',
            'AVATAR_CHANGE': 'info',
            'SHIPMENT_CREATE': 'success',
            'SHIPMENT_UPDATE': 'primary',
            'SHIPMENT_DELETE': 'danger',
            'SHIPMENT_STATUS': 'info',
            'SHIPMENT_VIEW': 'secondary',
            '2FA_TOGGLE': 'warning'
        }
        return color_map.get(self.action_type, 'secondary')

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        UserActivity.log_activity(
            user=instance,
            action_type='PROFILE_CREATE',
            description='Профиль пользователя создан'
        )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


class DashboardView(TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get('search', '')
        status_filter = self.request.GET.get('status', '')
        type_filter = self.request.GET.get('type', '')

        shipments = Shipment.objects.all().order_by('-timestamp')

        if search_query:
            shipments = shipments.filter(
                Q(waybill_number__icontains=search_query) |
                Q(city__icontains=search_query) |
                Q(id__icontains=search_query)
            )
        if status_filter:
            shipments = shipments.filter(status=status_filter)
        if type_filter:
            shipments = shipments.filter(type=type_filter)

        context.update({
            'total_shipments': shipments.count(),
            'created_count': shipments.filter(status='created').count(),
            'delivered_count': shipments.filter(status='delivered').count(),
            'problem_count': shipments.filter(status='problem').count(),
            'shipments': Paginator(shipments, 10).get_page(self.request.GET.get('page')),
            'search_query': search_query,
            'status_filter': status_filter,
            'type_filter': type_filter,
        })
        return context


def shipment_details(request, shipment_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)

    # Логирование просмотра деталей
    if request.user.is_authenticated:
        UserActivity.objects.create(
            user=request.user,
            action_type='SHIPMENT_VIEW',
            description=f'Просмотр деталей отправки #{shipment_id}',
            metadata={
                'shipment_id': shipment_id,
                'status': shipment.status
            }
        )

    context = {
        'shipment': shipment,
        'total_shipments': Shipment.objects.count(),
        'delivered_count': Shipment.objects.filter(status='delivered').count(),
        'created_count': Shipment.objects.filter(status='created').count(),
        'problem_count': Shipment.objects.filter(status='problem').count(),
    }
    return render(request, 'core/shipment_details.html', context)


class CustomLoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            messages.info(request, 'Вы уже авторизованы')
            return redirect('/')
        return render(request, 'registration/login.html')

    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            UserActivity.objects.create(
                user=user,
                action_type='LOGIN',
                description='Успешный вход в систему'
            )
            messages.success(request, f'Добро пожаловать, {user.username}!')
            return redirect('/')

        messages.error(request, 'Неверные имя пользователя или пароль')
        return render(request, 'registration/login.html', {'form': form})


@login_required
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    if created:
        messages.info(request, 'Профиль успешно создан')
        UserActivity.objects.create(
            user=request.user,
            action_type='PROFILE_CREATE',
            description='Создан новый профиль'
        )

    shipment_count = Shipment.objects.filter(user=request.user).count()
    delivered_count = Shipment.objects.filter(user=request.user, status='delivered').count()

    recent_actions = UserActivity.objects.filter(user=request.user).order_by('-timestamp')[:5]

    return render(request, 'core/profile.html', {
        'shipment_count': shipment_count,
        'delivered_count': delivered_count,
        'recent_actions': recent_actions,
        'current_session': 'Сейчас активен'
    })


@login_required
@transaction.atomic
def update_profile(request):
    if request.method == 'POST':
        user = request.user
        profile = Profile.objects.get(user=user)

        try:
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', '')
            user.save()

            profile.phone = request.POST.get('phone', '')
            profile.position = request.POST.get('position', '')
            profile.address = request.POST.get('address', '')
            profile.telegram_id = request.POST.get('telegram_id', '')
            profile.save()

            UserActivity.objects.create(
                user=user,
                action_type='PROFILE_UPDATE',
                description='Обновление профиля'
            )
            messages.success(request, 'Профиль успешно обновлен')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении профиля: {str(e)}')

        return redirect('profile')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('profile')


@login_required
def update_avatar(request):
    if request.method == 'POST':
        profile = Profile.objects.get(user=request.user)

        try:
            if 'avatar' in request.FILES:
                if profile.avatar:
                    profile.avatar.delete()
                profile.avatar = request.FILES['avatar']
                profile.save()
                UserActivity.objects.create(
                    user=request.user,
                    action_type='AVATAR_CHANGE',
                    description='Изменение аватара'
                )
                messages.success(request, 'Аватар успешно обновлен')
            else:
                messages.error(request, 'Не выбран файл для загрузки')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении аватара: {str(e)}')

        return redirect('profile')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('profile')


@login_required
def remove_avatar(request):
    if request.method == 'POST':
        profile = Profile.objects.get(user=request.user)

        try:
            if profile.avatar:
                profile.avatar.delete()
                profile.avatar = None
                profile.save()
                UserActivity.objects.create(
                    user=request.user,
                    action_type='AVATAR_CHANGE',
                    description='Удаление аватара'
                )
                messages.success(request, 'Аватар успешно удален')
            else:
                messages.warning(request, 'Аватар уже отсутствует')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении аватара: {str(e)}')

        return redirect('profile')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('profile')


@login_required
def update_password(request):
    if request.method == 'POST':
        user = request.user
        current_password = request.POST.get('current_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        try:
            if not user.check_password(current_password):
                messages.error(request, 'Неверный текущий пароль')
                return redirect('profile')

            if new_password1 != new_password2:
                messages.error(request, 'Новые пароли не совпадают')
                return redirect('profile')

            if len(new_password1) < 8:
                messages.error(request, 'Пароль должен содержать минимум 8 символов')
                return redirect('profile')

            user.set_password(new_password1)
            user.save()
            update_session_auth_hash(request, user)

            UserActivity.objects.create(
                user=user,
                action_type='PASSWORD_CHANGE',
                description='Изменение пароля'
            )
            messages.success(request, 'Пароль успешно изменен')
        except Exception as e:
            messages.error(request, f'Ошибка при изменении пароля: {str(e)}')

        return redirect('profile')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('profile')


@login_required
def toggle_2fa(request):
    if request.method == 'POST':
        profile = Profile.objects.get(user=request.user)
        enabled = request.POST.get('enabled') == 'true'

        try:
            profile.two_factor_enabled = enabled
            profile.save()

            action = 'включена' if enabled else 'отключена'
            UserActivity.objects.create(
                user=request.user,
                action_type='2FA_TOGGLE',
                description=f'Двухфакторная аутентификация {action}'
            )

            return JsonResponse({
                'success': True,
                'message': f'2FA успешно {action}',
                'enabled': enabled
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)

    return JsonResponse({
        'success': False,
        'message': 'Invalid request'
    }, status=400)


@login_required
def update_shipment_status(request, shipment_id):
    if request.method == 'POST':
        try:
            shipment = Shipment.objects.get(id=shipment_id)
            new_status = request.POST.get('status')
            old_status = shipment.get_status_display()

            shipment.status = new_status
            shipment.save()

            UserActivity.objects.create(
                user=request.user,
                action_type='SHIPMENT_STATUS',
                description=f'Изменение статуса отправки #{shipment_id}',
                metadata={
                    'old_status': old_status,
                    'new_status': shipment.get_status_display()
                }
            )

            messages.success(
                request,
                f'Статус отправки #{shipment_id} изменен: {old_status} → {shipment.get_status_display()}'
            )
        except Shipment.DoesNotExist:
            messages.error(request, f'Отправка #{shipment_id} не найдена')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении статуса: {str(e)}')

        return redirect('dashboard')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('dashboard')


@login_required
def create_shipment(request):
    if request.method == 'POST':
        try:
            # Здесь должна быть логика создания новой отправки
            # shipment = Shipment.objects.create(...)

            UserActivity.objects.create(
                user=request.user,
                action_type='SHIPMENT_CREATE',
                description='Создание новой отправки'
            )
            messages.success(request, 'Новая отправка успешно создана')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Ошибка при создании отправки: {str(e)}')
            return redirect('dashboard')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('dashboard')


@login_required
def delete_shipment(request, shipment_id):
    if request.method == 'POST':
        try:
            shipment = Shipment.objects.get(id=shipment_id)
            shipment.delete()

            UserActivity.objects.create(
                user=request.user,
                action_type='SHIPMENT_DELETE',
                description=f'Удаление отправки #{shipment_id}'
            )
            messages.success(request, f'Отправка #{shipment_id} успешно удалена')
        except Shipment.DoesNotExist:
            messages.error(request, f'Отправка #{shipment_id} не найдена')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении отправки: {str(e)}')

        return redirect('dashboard')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('dashboard')


def custom_404(request, exception):
    print(f"404 Error: {request.path} - {exception}")
    messages.warning(request, 'Страница, которую вы ищете, не существует')
    return render(request, 'core/errors/404.html', status=404)