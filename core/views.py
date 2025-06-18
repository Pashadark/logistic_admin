import io
import os
import zipfile
from django.views.generic import TemplateView
from django.core.paginator import Paginator
from cargo_admin.models import Shipment
from django.db.models import Q
from django.views import View
from django.contrib.auth import login, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.conf import settings
from .models import Profile, UserActivity
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()

def register_view(request):
    if request.user.is_authenticated:
        messages.warning(request, 'Вы уже авторизованы и будете перенаправлены')
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user)
                messages.success(request, 'Регистрация прошла успешно! Добро пожаловать!')
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f'Ошибка при создании пользователя: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Ошибка в поле "{field}": {error}')
    else:
        form = UserCreationForm()

    return render(request, 'registration/register_standalone.html', {'form': form})

def custom_login_view(request):
    if request.user.is_authenticated:
        messages.info(request, 'Вы уже авторизованы')
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            try:
                user = form.get_user()
                login(request, user)
                messages.success(request, f'Добро пожаловать, {user.username}!')
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f'Ошибка входа: {str(e)}')
        else:
            messages.error(request, 'Неверные имя пользователя или пароль')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login_standalone.html', {'form': form})

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
                Q(id__icontains=search_query))
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

def download_shipment_files(request, shipment_id):
    try:
        shipment = Shipment.objects.get(id=shipment_id)
        files_to_zip = []

        # Проверяем и добавляем файлы в архив
        for file_field in ['waybill_photo', 'product_photo']:
            file = getattr(shipment, file_field)
            if file:
                file_path = os.path.join(settings.MEDIA_ROOT, str(file))
                if os.path.exists(file_path):
                    files_to_zip.append((file_path, os.path.basename(file_path)))

        if not files_to_zip:
            messages.warning(request, 'Нет файлов для скачивания')
            return redirect('shipment_details', shipment_id=shipment_id)

        # Создаем архив
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_path, arcname in files_to_zip:
                zip_file.write(file_path, arcname)

        zip_buffer.seek(0)
        response = FileResponse(zip_buffer, as_attachment=True,
                              filename=f'shipment_{shipment_id}_files.zip')
        response['Content-Type'] = 'application/zip'
        return response

    except Shipment.DoesNotExist:
        messages.error(request, f'Отправка #{shipment_id} не найдена')
        return redirect('dashboard')
    except Exception as e:
        messages.error(request, f'Ошибка при создании архива: {str(e)}')
        return redirect('shipment_details', shipment_id=shipment_id)

def shipment_details(request, shipment_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)

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

    # Исправляем фильтрацию - используем user_id вместо user
    shipment_count = Shipment.objects.filter(user_id=request.user.id).count()
    delivered_count = Shipment.objects.filter(user_id=request.user.id, status='delivered').count()

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
        try:
            user = request.user
            profile = Profile.objects.get(user=user)

            # Валидация email
            new_email = request.POST.get('email', '')
            if new_email and User.objects.exclude(pk=user.pk).filter(email=new_email).exists():
                messages.error(request, 'Этот email уже используется другим пользователем')
                return redirect('profile')

            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = new_email
            user.save()

            profile.phone = request.POST.get('phone', '')
            if profile.phone and not profile.phone.isdigit():
                messages.error(request, 'Номер телефона должен содержать только цифры')
                return redirect('profile')

            profile.position = request.POST.get('position', '')
            profile.address = request.POST.get('address', '')
            profile.telegram_id = request.POST.get('telegram_id', '')
            profile.save()

            messages.success(request, 'Профиль успешно обновлен')
            UserActivity.log_activity(
                user=user,
                action_type='PROFILE_UPDATE',
                description='Обновление профиля'
            )
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении профиля: {str(e)}')

        return redirect('profile')

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('profile')

@login_required
def update_avatar(request):
    if request.method == 'POST':
        try:
            profile = Profile.objects.get(user=request.user)

            if 'avatar' not in request.FILES:
                messages.error(request, 'Файл аватара не выбран')
                return redirect('profile')

            avatar = request.FILES['avatar']

            # Проверка размера файла (до 2MB)
            if avatar.size > 2 * 1024 * 1024:
                messages.error(request, 'Размер файла не должен превышать 2MB')
                return redirect('profile')

            # Проверка типа файла
            if not avatar.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                messages.error(request, 'Поддерживаются только JPG/JPEG/PNG файлы')
                return redirect('profile')

            if profile.avatar:
                profile.avatar.delete()

            profile.avatar = avatar
            profile.save()

            messages.success(request, 'Аватар успешно обновлен')
            UserActivity.log_activity(
                user=request.user,
                action_type='AVATAR_CHANGE',
                description='Изменение аватара'
            )
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
                messages.error(request, 'Текущий пароль введен неверно')
                return redirect('profile')

            if new_password1 != new_password2:
                messages.error(request, 'Новые пароли не совпадают')
                return redirect('profile')

            if len(new_password1) < 8:
                messages.error(request, 'Пароль должен содержать минимум 8 символов')
                return redirect('profile')

            if new_password1 == current_password:
                messages.warning(request, 'Новый пароль должен отличаться от текущего')
                return redirect('profile')

            user.set_password(new_password1)
            user.save()
            update_session_auth_hash(request, user)

            messages.success(request, 'Пароль успешно изменен')
            UserActivity.log_activity(
                user=user,
                action_type='PASSWORD_CHANGE',
                description='Изменение пароля'
            )
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

            if not new_status:
                messages.error(request, 'Не выбран новый статус')
                return redirect('dashboard')

            old_status = shipment.get_status_display()

            # Проверка допустимости перехода статуса
            valid_transitions = {
                'created': ['processing', 'problem'],
                'processing': ['transit', 'problem'],
                'transit': ['delivered', 'problem'],
                'problem': ['processing', 'transit'],
                'delivered': []
            }

            if new_status not in valid_transitions.get(shipment.status, []):
                messages.warning(request,
                               f'Недопустимый переход статуса: {shipment.status} → {new_status}')
                return redirect('dashboard')

            shipment.status = new_status
            shipment.save()

            messages.success(
                request,
                f'Статус отправки #{shipment_id} изменен: {old_status} → {shipment.get_status_display()}'
            )
            UserActivity.log_activity(
                user=request.user,
                action_type='SHIPMENT_STATUS',
                description=f'Изменение статуса отправки #{shipment_id}',
                metadata={
                    'old_status': old_status,
                    'new_status': shipment.get_status_display()
                }
            )
        except Shipment.DoesNotExist:
            messages.error(request, f'Отправка #{shipment_id} не найдена')
            return redirect('dashboard')
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
    messages.error(request,
                 f'Страница {request.path} не найдена. Проверьте URL или перейдите на главную')
    return render(request, 'core/errors/404.html', status=404)