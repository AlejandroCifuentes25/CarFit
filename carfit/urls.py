"""Configuración de URLs del proyecto CarFit."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/', include('django.contrib.auth.urls')),
    # La API vive bajo un prefijo propio para que un API Gateway pueda
    # enrutarla por separado del front web sin tocar el código.
    path('api/', include('marketplace.api.urls')),
    path('', include('marketplace.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
