from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import Http404


def raise_404(request):
    raise Http404("Тестовая страница 404")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('test-404/', raise_404),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
handler404 = 'core.views.custom_404'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)