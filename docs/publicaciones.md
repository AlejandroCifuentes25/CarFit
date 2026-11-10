# Flujos web de publicación y gestión (Flask)

Servicio `publications_microservice.py` (puerto 5003, `Dockerfile.publications`,
servicio `publications` en `docker-compose.yml`). Patrón strangler: Nginx envía
`/publicaciones/v2/` a Flask; las páginas Django originales siguen activas como
legado/rollback.

Para acceder a través de Nginx en `http://127.0.0.1:8000`, inicia el stack
integrado con `docker compose up --build` y usa las rutas `/publicaciones/v2/`.
El puerto 8000 del host publica Nginx (puerto 80 del contenedor); no uses
`python manage.py runserver` en ese mismo puerto mientras el stack está activo.
Las rutas Django antiguas siguen disponibles a través del mismo gateway y la
navegación principal conserva esos enlaces.

| Flask (nuevo) | Django (legado) |
|---|---|
| `/publicaciones/v2/nuevo/` | `/articulos/nuevo/` |
| `/publicaciones/v2/nuevo/repuesto/` | `/articulos/nuevo/repuesto/` |
| `/publicaciones/v2/publicado/` | `/articulos/publicado/` |
| `/publicaciones/v2/mis-publicaciones/` | `/mis-publicaciones/` |
| `/publicaciones/v2/editar/<carro\|repuesto>/<pk>/` | `/articulos/editar/<tipo>/<pk>/` |
| `/publicaciones/v2/eliminar/<carro\|repuesto>/<pk>/` | `/articulos/eliminar/<tipo>/<pk>/` |
| `/publicaciones/v2/health` | — |

Comportamiento:
- Comparte sesión de Django (cookie y `SESSION_ENGINE`) con el servicio de cuentas;
  sin sesión redirige a `/cuentas/login/?next=...`; sin perfil de vendedor responde 403.
- CSRF: token ligado a la sesión (mismos helpers que `accounts_microservice`),
  campo oculto `_csrf_token`; los POST sin token válido responden 403.
- Reutiliza formularios y `PublicacionArticuloService` de Django, por lo que las reglas
  de negocio no se duplican. Edición y borrado se limitan a artículos del vendedor (404 si no).
- Rollback: quitar el bloque `location /publicaciones/v2/` de `nginx/nginx.conf`.
- El menú del sitio conserva los enlaces a Django (`/articulos/nuevo/` y
  `/mis-publicaciones/`); para probar el slice Flask, navega a `/publicaciones/v2/`.

Pruebas: `python manage.py test marketplace.tests.test_publications_microservice`.
