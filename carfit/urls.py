"""Configuración de URLs del proyecto CarFit."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.vary import vary_on_cookie
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path(
        'i18n/carfit.js',
        vary_on_cookie(JavaScriptCatalog.as_view(packages=['marketplace'])),
        name='carfit_js_i18n',
    ),
    path('admin/', admin.site.urls),
    path('cuentas/', include('django.contrib.auth.urls')),
    # La API vive bajo un prefijo propio para que un API Gateway pueda
    # enrutarla por separado del front web sin tocar el código.
    path('api/', include('marketplace.api.urls')),
    path('api/', include('marketplace.api.urls_cuentas')),
    path('', include('marketplace.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
