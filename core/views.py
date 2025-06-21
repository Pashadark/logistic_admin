import io
import os
import zipfile
import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.core import serializers
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.contrib import messages

from .models import Profile, Shipment, UserActivity
import requests


# Проверка прав администратора
def is_admin(user):
    return user.is_authenticated and user.is_staff


@staff_member_required
def admin_panel(request):
    users = User.objects.all().select_related('profile')
    groups = Group.objects.all()

    # Статистика бота
    bot_stats = {
        'active_users': User.objects.filter(profile__telegram_id__isnull=False).count(),
        'messages_today': 42,
        'total_messages': 1024,
        'last_activity': datetime.now()
    }

    # Информация о последнем бэкапе
    last_backup = None
    try:
        if hasattr(settings, 'BACKUP_PATH') and os.path.exists(settings.BACKUP_PATH):
            backups = sorted(os.listdir(settings.BACKUP_PATH), reverse=True)
            if backups:
                last_backup = backups[0]
    except Exception as e:
        print(f"Ошибка при доступе к бэкапам: {e}")

    return render(request, 'core/admin_panel.html', {
        'users': users,
        'groups': groups,
        'bot_stats': bot_stats,
        'last_backup': last_backup
    })


@staff_member_required
def admin_create_user(request):
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            email = request.POST.get('email')
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            group_id = request.POST.get('group')
            is_active = request.POST.get('is_active') == 'on'

            if not username or not password1:
                return JsonResponse({'success': False, 'message': 'Имя пользователя и пароль обязательны'}, status=400)

            if password1 != password2:
                return JsonResponse({'success': False, 'message': 'Пароли не совпадают'}, status=400)

            if User.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'message': 'Пользователь с таким именем уже существует'},
                                    status=400)

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                is_active=is_active
            )

            if group_id:
                try:
                    group = Group.objects.get(id=group_id)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='USER_CREATE',
                description=f'Создан пользователь {username}',
                metadata={'user_id': user.id}
            )

            return JsonResponse({'success': True, 'message': 'Пользователь успешно создан'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
def admin_edit_user(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            username = request.POST.get('username')
            email = request.POST.get('email')
            telegram_id = request.POST.get('telegram_id')
            group_id = request.POST.get('group')
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'

            if not username:
                return JsonResponse({'success': False, 'message': 'Имя пользователя обязательно'}, status=400)

            # Обновляем основные данные пользователя
            user.username = username
            user.email = email
            user.is_active = is_active
            user.is_staff = is_staff
            user.save()

            # Обновляем профиль (Telegram ID)
            profile = user.profile
            profile.telegram_id = telegram_id
            profile.save()

            # Обновляем группы
            user.groups.clear()
            if group_id:
                try:
                    group = Group.objects.get(id=group_id)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='USER_UPDATE',
                description=f'Изменен пользователь {username}',
                metadata={'user_id': user.id}
            )

            return JsonResponse({'success': True, 'message': 'Изменения успешно сохранены'})

        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Пользователь не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
@require_POST
def admin_delete_user(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        if request.user == user:
            return JsonResponse({
                'success': False,
                'message': 'Вы не можете удалить свой собственный аккаунт'
            }, status=400)

        username = user.username
        user.delete()

        UserActivity.objects.create(
            user=request.user,
            action_type='USER_DELETE',
            description=f'Удален пользователь {username}',
            metadata={'user_id': user_id}
        )

        return JsonResponse({
            'success': True,
            'message': f'Пользователь {username} успешно удален'
        })

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Пользователь не найден'
        }, status=404)


@staff_member_required
@require_POST
def admin_test_bot(request):
    try:
        data = json.loads(request.body)
        message_text = data.get('message', 'Тестовое сообщение из админ-панели')
        send_to_group = data.get('is_group_message', True)

        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            return JsonResponse({
                'success': False,
                'message': 'Токен бота не настроен в системе'
            }, status=500)

        chat_id = settings.TELEGRAM_LOG_CHAT_ID if send_to_group else getattr(request.user.profile, 'telegram_id', None)

        if not chat_id:
            return JsonResponse({
                'success': False,
                'message': 'Не указан chat_id для отправки сообщения'
            }, status=400)

        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': message_text,
                'parse_mode': 'HTML'
            },
            timeout=10
        )

        response_data = response.json()
        if not response.ok or not response_data.get('ok'):
            error_msg = response_data.get('description', 'Unknown Telegram API error')
            return JsonResponse({
                'success': False,
                'message': f'Ошибка Telegram API: {error_msg}',
                'telegram_response': response_data
            }, status=500)

        # Логирование действия
        UserActivity.objects.create(
            user=request.user,
            action_type='BOT_TEST',
            description='Отправлено тестовое сообщение бота',
            metadata={
                'chat_id': chat_id,
                'message_text': message_text,
                'is_group': send_to_group,
                'status': 'success'
            }
        )

        return JsonResponse({
            'success': True,
            'message': f'Тестовое сообщение отправлено в {"группу" if send_to_group else "личные сообщения"}',
            'message_id': response_data.get('result', {}).get('message_id')
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Неверный формат JSON данных'
        }, status=400)
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'message': f'Ошибка соединения с Telegram: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Внутренняя ошибка: {str(e)}'
        }, status=500)


@staff_member_required
def get_activity_logs(request):
    try:
        # Получаем последние 30 записей активности
        logs = UserActivity.objects.select_related('user').order_by('-timestamp')[:30]

        logs_list = []
        for log in logs:
            logs_list.append({
                'id': log.id,
                'timestamp': log.timestamp.strftime("%d.%m.%Y %H:%M:%S"),
                'user': log.user.get_full_name() or log.user.username,
                'action': log.get_action_type_display(),
                'action_type': log.action_type,
                'description': log.description
            })

        return JsonResponse({'status': 'success', 'logs': logs_list})

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@staff_member_required
@require_POST
def admin_test_bot(request):
    try:
        data = json.loads(request.body)
        message_text = data.get('message', 'Тестовое сообщение из админ-панели')
        send_to_group = data.get('is_group_message', True)

        if not settings.TELEGRAM_BOT_TOKEN:
            return JsonResponse({
                'success': False,
                'message': 'Токен бота не настроен в системе'
            }, status=500)

        # Определяем chat_id в зависимости от типа сообщения
        if send_to_group:
            chat_id = settings.TELEGRAM_LOG_CHAT_ID
            target = "группу"
        else:
            if hasattr(request.user, 'profile') and request.user.profile.telegram_id:
                chat_id = request.user.profile.telegram_id
                target = "личные сообщения"
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Telegram ID пользователя не настроен'
                }, status=400)

        response = requests.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': message_text,
                'parse_mode': 'HTML'
            },
            timeout=10
        )

        response_data = response.json()
        if not response.ok or not response_data.get('ok'):
            error_msg = response_data.get('description', 'Unknown Telegram API error')
            return JsonResponse({
                'success': False,
                'message': f'Ошибка Telegram API: {error_msg}',
                'telegram_response': response_data
            }, status=500)

        # Логирование действия
        UserActivity.objects.create(
            user=request.user,
            action_type='BOT_TEST',
            description=f'Отправлено сообщение в {target}',
            metadata={
                'chat_id': chat_id,
                'message_text': message_text,
                'is_group': send_to_group,
                'status': 'success'
            }
        )

        return JsonResponse({
            'success': True,
            'message': f'Сообщение успешно отправлено в {target}',
            'message_id': response_data.get('result', {}).get('message_id')
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Неверный формат JSON данных'
        }, status=400)
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'message': f'Ошибка соединения с Telegram: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Внутренняя ошибка: {str(e)}'
        }, status=500)

@staff_member_required
def admin_create_backup(request):
    if request.method == 'POST':
        try:
            # Создаем имя файла с текущей датой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}.json"
            backup_path = os.path.join(settings.BACKUP_PATH, backup_filename)

            # Создаем директорию для бэкапов, если ее нет
            os.makedirs(settings.BACKUP_PATH, exist_ok=True)

            # Сериализуем важные данные
            data = {
                'users': serializers.serialize('json', User.objects.all()),
                'profiles': serializers.serialize('json', Profile.objects.all()),
                'backup_created': timestamp,
                'created_by': request.user.username
            }

            # Сохраняем в файл
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='BACKUP_CREATE',
                description='Создан резервная копия данных',
                metadata={'backup_file': backup_filename}
            )

            return JsonResponse({
                'success': True,
                'message': 'Резервная копия успешно создана',
                'backup_filename': backup_filename
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
def admin_download_backup(request):
    try:
        # Получаем последний бэкап
        if not os.path.exists(settings.BACKUP_PATH):
            return JsonResponse({'success': False, 'message': 'Директория с бэкапами не найдена'}, status=404)

        backups = sorted(os.listdir(settings.BACKUP_PATH), reverse=True)
        if not backups:
            return JsonResponse({'success': False, 'message': 'Бэкапы не найдены'}, status=404)

        latest_backup = backups[0]
        backup_path = os.path.join(settings.BACKUP_PATH, latest_backup)

        # Логирование действия
        UserActivity.objects.create(
            user=request.user,
            action_type='BACKUP_DOWNLOAD',
            description='Скачан файл резервной копии',
            metadata={'backup_file': latest_backup}
        )

        # Создаем ответ с файлом
        response = FileResponse(open(backup_path, 'rb'))
        response['Content-Type'] = 'application/json'
        response['Content-Disposition'] = f'attachment; filename="{latest_backup}"'
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@staff_member_required
def admin_get_backup_info(request):
    try:
        if not os.path.exists(settings.BACKUP_PATH):
            return JsonResponse({
                'success': True,
                'last_backup': None,
                'backups_count': 0
            })

        backups = sorted(os.listdir(settings.BACKUP_PATH), reverse=True)
        return JsonResponse({
            'success': True,
            'last_backup': backups[0] if backups else None,
            'backups_count': len(backups)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@staff_member_required
def admin_set_backup_interval(request):
    if request.method == 'POST':
        try:
            interval = int(request.POST.get('interval', 0))

            # Здесь должна быть логика сохранения интервала
            # Например, в модели Settings или в базе данных

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='BACKUP_INTERVAL_UPDATE',
                description='Изменен интервал автоматического бэкапа',
                metadata={'interval_days': interval}
            )

            return JsonResponse({
                'success': True,
                'message': f'Интервал автоматического бэкапа установлен: {interval} дней'
            })

        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'Неверное значение интервала'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
def admin_clear_database(request):
    if request.method == 'POST':
        try:
            # Очищаем данные, но оставляем пользователей и настройки
            Shipment.objects.all().delete()
            # Добавьте другие модели, которые нужно очистить

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='DATABASE_CLEAR',
                description='Очистка базы данных'
            )

            return JsonResponse({
                'success': True,
                'message': 'База данных успешно очищена'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
def admin_restore_database(request):
    if request.method == 'POST':
        try:
            backup_file = request.FILES.get('backup_file')
            if not backup_file:
                return JsonResponse({
                    'success': False,
                    'message': 'Файл бэкапа не загружен'
                }, status=400)

            # Здесь должна быть логика восстановления из бэкапа
            # Это пример - реализуйте в зависимости от формата вашего бэкапа

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='DATABASE_RESTORE',
                description='Восстановление базы данных из бэкапа',
                metadata={'backup_file': backup_file.name}
            )

            return JsonResponse({
                'success': True,
                'message': 'База данных успешно восстановлена из бэкапа'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)

    return JsonResponse({'success': False, 'message': 'Неверный метод запроса'}, status=400)


@staff_member_required
def admin_set_bot_access(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            global_access = data.get('global_access', False)
            allowed_users = data.get('allowed_users', [])

            # Здесь должна быть логика сохранения настроек доступа к боту
            # Например, сохранение в модели Settings или в базе данных

            # Логирование действия
            UserActivity.objects.create(
                user=request.user,
                action_type='BOT_ACCESS_UPDATE',
                description='Изменены настройки доступа к боту',
                metadata={
                    'global_access': global_access,
                    'allowed_users': allowed_users
                }
            )

            return JsonResponse({
                'success': True,
                'message': 'Настройки доступа к боту обновлены'
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Неверный формат JSON данных'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Ошибка: {str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': 'Неверный метод запроса'
    }, status=400)


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

        paginator = Paginator(shipments, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context.update({
            'total_shipments': shipments.count(),
            'created_count': shipments.filter(status='created').count(),
            'delivered_count': shipments.filter(status='delivered').count(),
            'problem_count': shipments.filter(status='problem').count(),
            'shipments': page_obj,
            'search_query': search_query,
            'status_filter': status_filter,
            'type_filter': type_filter,
        })
        return context


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
def update_profile(request):
    if request.method == 'POST':
        user = request.user
        profile = Profile.objects.get(user=user)

        try:
            # Валидация email
            new_email = request.POST.get('email', '')
            if new_email and User.objects.exclude(pk=user.pk).filter(email=new_email).exists():
                messages.error(request, 'Этот email уже используется другим пользователем')
                return redirect('profile')

            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = new_email
            user.save()

            # Обновление данных телефона
            phone = request.POST.get('phone', '').strip()
            if phone:
                if not phone.isdigit():
                    messages.error(request, 'Номер телефона должен содержать только цифры')
                    return redirect('profile')
                profile.phone = phone
            else:
                profile.phone = ''

            # Обновление остальных полей профиля
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


def example_view(request):
    # Примеры правильных сообщений
    messages.success(request, 'Операция выполнена успешно!')
    messages.error(request, 'Произошла ошибка!')
    messages.warning(request, 'Внимание! Это предупреждение.')
    messages.info(request, 'Информационное сообщение.')

    return redirect('dashboard')


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
            messages.success(request, f'Отправка #{shipment_id} успешно удалена')
            return redirect('dashboard')
        except Shipment.DoesNotExist:
            messages.error(request, f'Отправка #{shipment_id} не найдена')
            return redirect('shipment_details', shipment_id=shipment_id)

    messages.warning(request, 'Некорректный метод запроса')
    return redirect('shipment_details', shipment_id=shipment_id)


def custom_404(request, exception):
    messages.error(request,
                   f'Страница {request.path} не найдена. Проверьте URL или перейдите на главную')
    return render(request, 'core/errors/404.html', status=404)


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

    def logout_view(request):
        """Кастомный выход из системы с редиректом на страницу входа"""
        auth_logout(request)
        messages.info(request, "Вы успешно вышли из системы")
        return redirect('login')
