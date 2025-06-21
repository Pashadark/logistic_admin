from django.contrib import admin
from django.http import HttpResponse
import csv
from django.db.models import Q
from django.utils.html import format_html
from core.models import Profile, Shipment
from .forms import ShipmentFilterForm  # Убедитесь, что этот импорт корректный

# Модель Profile
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'position')
    search_fields = ('user__username', 'user__email', 'phone')
    list_select_related = ('user',)

# Модель Shipment
@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_type_display',
        'waybill_number',
        'city',
        'get_status_badge',
        'timestamp',
        'actions_column'
    )
    list_filter = ('type', 'status', 'city', 'timestamp')
    search_fields = ('waybill_number', 'city', 'comment')
    ordering = ('-timestamp',)
    list_per_page = 20
    actions = ['export_to_csv']
    change_list_template = 'admin/cargo_admin/shipment_change_list.html'

    # Методы для Shipment
    def get_type_display(self, obj):
        return obj.get_type_display()
    get_type_display.short_description = 'Тип операции'

    def get_status_badge(self, obj):
        status_colors = {
            'created': 'info',
            'processing': 'primary',
            'transit': 'warning',
            'delivered': 'success',
            'problem': 'danger',
        }
        color = status_colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_status_display()
        )
    get_status_badge.short_description = 'Статус'
    get_status_badge.admin_order_field = 'status'

    def actions_column(self, obj):
        return format_html(
            '<a href="/admin/cargo_admin/shipment/{}/change/" class="btn btn-sm btn-outline-primary">✏️</a>'
            ' <a href="/admin/cargo_admin/shipment/{}/delete/" class="btn btn-sm btn-outline-danger">🗑️</a>',
            obj.id, obj.id
        )
    actions_column.short_description = 'Действия'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['filter_form'] = ShipmentFilterForm(request.GET)
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if 'search' in request.GET:
            form = ShipmentFilterForm(request.GET)
            if form.is_valid():
                if form.cleaned_data['search']:
                    search = form.cleaned_data['search']
                    qs = qs.filter(
                        Q(waybill_number__icontains=search) |
                        Q(city__icontains=search) |
                        Q(comment__icontains=search)
                    )

                if form.cleaned_data['status']:
                    qs = qs.filter(status=form.cleaned_data['status'])

                if form.cleaned_data['type']:
                    qs = qs.filter(type=form.cleaned_data['type'])

                if form.cleaned_data['date_from']:
                    qs = qs.filter(timestamp__gte=form.cleaned_data['date_from'])

                if form.cleaned_data['date_to']:
                    qs = qs.filter(timestamp__lte=form.cleaned_data['date_to'])

        return qs

    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="shipments.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'User ID', 'Type', 'Waybill Number',
            'City', 'Status', 'Comment', 'Timestamp'
        ])

        for obj in queryset:
            writer.writerow([
                obj.id, obj.user_id, obj.get_type_display(),
                obj.waybill_number, obj.city, obj.get_status_display(),
                obj.comment, obj.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ])

        return response
    export_to_csv.short_description = "Экспорт выбранных в CSV"