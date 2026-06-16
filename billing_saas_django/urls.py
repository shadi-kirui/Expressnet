from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from billing_api.views import react_app, react_asset


urlpatterns = [
    path("api/", include("billing_api.urls")),
    path("assets/<path:asset_path>", react_asset, name="react_asset"),
    re_path(r"^(?!api/).*", react_app, name="react_app"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "frontend" / "dist" / "assets")
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
