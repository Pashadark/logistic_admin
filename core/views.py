from django.views.generic import TemplateView
from django.core.paginator import Paginator
from cargo_admin.models import Shipment
from django.db.models import Q


class DashboardView(TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters
        search_query = self.request.GET.get('search', '')
        status_filter = self.request.GET.get('status', '')
        type_filter = self.request.GET.get('type', '')

        # Get all shipments with filters
        shipments = Shipment.objects.all().order_by('-timestamp')

        # Apply filters
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

        # Statistics
        context['total_shipments'] = shipments.count()
        context['created_count'] = shipments.filter(status='created').count()
        context['delivered_count'] = shipments.filter(status='delivered').count()
        context['problem_count'] = shipments.filter(status='problem').count()

        # Pagination
        paginator = Paginator(shipments, 10)
        page_number = self.request.GET.get('page')
        shipments_page = paginator.get_page(page_number)

        context['shipments'] = shipments_page
        context['search_query'] = search_query
        context['status_filter'] = status_filter
        context['type_filter'] = type_filter

        return context


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from .models import Profile


@login_required
def profile_view(request):
    # Получаем или создаем профиль пользователя
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Статистика для отображения (пример)
    shipment_count = 42  # Замените на реальные данные
    delivered_count = 38  # Замените на реальные данные

    # Последние действия (пример)
    recent_actions = [
        {
            'title': 'Создана новая отправка',
            'description': 'Отправка #12345 в Москву',
            'timestamp': '2023-10-15 14:30',
            'color': 'primary'
        },
        {
            'title': 'Обновлен статус отправки',
            'description': 'Отправка #12345 доставлена',
            'timestamp': '2023-10-16 09:15',
            'color': 'success'
        },
        {
            'title': 'Изменен профиль',
            'description': 'Обновлена контактная информация',
            'timestamp': '2023-10-17 11:20',
            'color': 'info'
        }
    ]

    return render(request, 'core/profile.html', {
        'shipment_count': shipment_count,
        'delivered_count': delivered_count,
        'recent_actions': recent_actions,
        'current_session': 'Сейчас активен'
    })


@login_required
def update_profile(request):
    if request.method == 'POST':
        user = request.user
        profile, created = Profile.objects.get_or_create(user=user)

        # Обновляем данные пользователя
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        user.save()

        # Обновляем профиль
        profile.phone = request.POST.get('phone', '')
        profile.position = request.POST.get('position', '')
        profile.address = request.POST.get('address', '')
        profile.telegram_id = request.POST.get('telegram_id', '')
        profile.save()

        messages.success(request, 'Профиль успешно обновлен')
        return redirect('profile')

    return redirect('profile')


@login_required
def update_avatar(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)

        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
            profile.save()
            messages.success(request, 'Аватар успешно обновлен')
        else:
            messages.error(request, 'Не выбран файл для загрузки')

        return redirect('profile')

    return redirect('profile')


@login_required
def remove_avatar(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)

        if profile.avatar:
            profile.avatar.delete()
            profile.avatar = None
            profile.save()
            messages.success(request, 'Аватар успешно удален')
        else:
            messages.warning(request, 'Аватар уже отсутствует')

        return redirect('profile')

    return redirect('profile')


@login_required
def update_password(request):
    if request.method == 'POST':
        user = request.user
        current_password = request.POST.get('current_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        # Проверка текущего пароля
        if not user.check_password(current_password):
            messages.error(request, 'Неверный текущий пароль')
            return redirect('profile')

        # Проверка совпадения новых паролей
        if new_password1 != new_password2:
            messages.error(request, 'Новые пароли не совпадают')
            return redirect('profile')

        # Обновление пароля
        user.set_password(new_password1)
        user.save()

        # Обновление сессии
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)

        messages.success(request, 'Пароль успешно изменен')
        return redirect('profile')

    return redirect('profile')


@login_required
def toggle_2fa(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)
        enabled = request.POST.get('enabled') == 'true'

        # В реальном приложении здесь будет логика включения/выключения 2FA
        profile.two_factor_enabled = enabled
        profile.save()

        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'message': 'Invalid request'})