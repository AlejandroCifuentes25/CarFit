"""Usa el mismo catálogo gettext y la misma cookie que el sitio Django."""
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils import translation
from flask import g, request


def instalar_i18n(app):
    app.jinja_env.add_extension("jinja2.ext.i18n")
    app.jinja_env.install_gettext_callables(
        translation.gettext, translation.ngettext, newstyle=True,
    )
    csrf = CsrfViewMiddleware(lambda req: HttpResponse())

    @app.before_request
    def activar_idioma():
        puente = HttpRequest()
        puente.COOKIES = request.cookies
        puente.META["HTTP_ACCEPT_LANGUAGE"] = request.headers.get("Accept-Language", "")
        g.solicitud_idioma = puente
        g.idioma = translation.get_language_from_request(puente)
        g.contexto_idioma = translation.override(g.idioma)
        g.contexto_idioma.__enter__()
        csrf.process_request(puente)

    @app.context_processor
    def contexto_selector():
        return {
            "idioma_actual": g.idioma,
            "idioma_csrf": get_token(g.solicitud_idioma),
            "idioma_next": request.full_path.removesuffix("?"),
        }

    @app.after_request
    def cabeceras_idioma(response):
        response.headers.setdefault("Content-Language", g.idioma)
        response.vary.update(["Accept-Language", "Cookie"])
        salida = csrf.process_response(g.solicitud_idioma, HttpResponse())
        for cookie in salida.cookies.values():
            response.headers.add("Set-Cookie", cookie.OutputString())
        return response

    @app.teardown_request
    def restaurar_idioma(error):
        contexto = g.pop("contexto_idioma", None)
        if contexto is not None:
            contexto.__exit__(None, None, None)
