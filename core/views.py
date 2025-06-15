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