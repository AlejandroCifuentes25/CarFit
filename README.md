**integrantes:**

Julian Jimenez Garcia

Simon Mazo Gomez

Alejandro Cifuentes Arroyave

# CarFit

Marketplace que **facilita y centraliza la compra y venta de repuestos y carros
en un solo lugar**, de manera fácil y adaptada a las necesidades de cada usuario.

## Funcionalidades integradas

Esta versión reúne los tres frentes de trabajo del equipo:

- **Administración y cuentas:** CRUD REST para carros, clientes y vendedores;
  registro e inicio de sesión.
- **Carrito de compras:** agregar, quitar, vaciar, calcular total y confirmar
  artículos antes del pago.
- **Pagos:** catálogo de métodos, creación y consulta de pagos, confirmación
  de pagos pendientes y factura.

Los permisos se aplican por rol: los **vendedores** publican vehículos y los
**clientes** compran, usan el carrito y consultan sus pagos.


## Arquitectura

La funcionalidad crítica refactorizada es **Crear Artículo** (publicación de un
vehículo por parte de un vendedor). Está organizada en capas, con las
dependencias apuntando siempre hacia el dominio:

```
marketplace/
├── views.py            # Capa de Interfaz:  CBV, solo traduce HTTP
├── forms.py            #                     valida formato, no reglas de negocio
├── api/                # Capa de Presentación (DRF): APIView + Serializers
│   ├── serializers.py  #   validan formato, no reglas de negocio
│   ├── views.py        #   una APIView por recurso, sin lógica
│   ├── errores.py      #   traduce errores de dominio a códigos HTTP
│   ├── urls.py         #   rutas de pagos y carrito
│   └── urls_cuentas.py #   rutas de login y CRUD administrativo
├── services.py         # Capa de Aplicación: orquesta los casos de uso
├── domain/             # Capa de Dominio:   reglas de negocio, sin Django ni HTTP
│   ├── builders.py     #   Patrón Builder (Fluent Interface)
│   ├── metodos_pago.py #   catálogo de métodos de pago y sus reglas
│   ├── facturas.py     #   generación de facturas
│   ├── ports.py        #   Interfaces abstractas (Inversión de Dependencias)
│   └── exceptions.py
├── infra/              # Infraestructura:   detalles reemplazables
│   ├── factories.py    #   Patrón Factory (MOCK vs REAL por variable de entorno)
│   ├── pasarelas.py    #   simulada, agregador de pagos y corresponsal
│   ├── validadores.py
│   └── notificadores.py
└── models.py           # Persistencia:      sin lógica de negocio
```

El segundo caso de uso implementado es **Pagar un Artículo**, con soporte para
tarjeta de crédito y débito, PSE, billetera digital y efectivo en corresponsal.
Está documentado en detalle (diagrama de secuencia, contrato de la API y
justificación de los patrones) en [docs/pagos.md](docs/pagos.md).


## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Stack integrado con Nginx y Flask

Para probar las rutas de Flask detrás del API Gateway, usa Docker Compose en
lugar de ejecutar Django con `runserver` en el puerto 8000:

```bash
docker compose up --build
```

Nginx queda disponible en <http://127.0.0.1:8000/>. Las páginas Flask de
publicación y compras están en `/publicaciones/v2/` y `/compras/v2/`; las rutas
web antiguas de Django siguen disponibles, por ejemplo `/articulos/nuevo/`,
`/mis-publicaciones/`, `/comprar/` y `/carrito/`.
No ejecutes a la vez `runserver` y Compose usando el mismo puerto del host.
El origen local de Nginx está permitido para las verificaciones CSRF de Django.
Si cambias el dominio o puerto, actualiza `CSRF_TRUSTED_ORIGINS` con los
orígenes completos, incluyendo el esquema (`http://` o `https://`).

Después de aplicar las migraciones queda incluido el esquema de carrito y
pagos. Para comprobar la instalación completa, ejecuta:

```bash
python manage.py check
python manage.py test marketplace
```

### Recorrido rápido

1. Abre <http://127.0.0.1:8000/registro/> para crear una cuenta de cliente o
   vendedor.
2. Una cuenta de **vendedor** puede publicar en
   <http://127.0.0.1:8000/publicaciones/v2/nuevo/>.
3. Una cuenta de **cliente** puede recorrer el catálogo en
   <http://127.0.0.1:8000/compras/v2/catalogo/> y usar el carrito en
   <http://127.0.0.1:8000/compras/v2/carrito/>.
4. Como alternativa, entra a <http://127.0.0.1:8000/admin/> con un
   superusuario para administrar clientes, vendedores y publicaciones.

Por defecto la app corre en modo **MOCK**: aprueba cualquier documento y
notifica por consola, sin necesidad de configurar nada. `.env.example` lista
las variables que se pueden **exportar en la terminal** para cambiar a modo
`REAL` (el proyecto no carga `.env` automáticamente, no existe `python-dotenv`
como dependencia, hay que exportarlas a mano si las quieres probar):

```bash
# PowerShell
$env:VALIDADOR_DOCUMENTAL = "REAL"
$env:NOTIFICADOR = "REAL"
python manage.py runserver
```


## API de pagos

Para probarla necesitas un `Cliente` asociado a tu usuario (**Marketplace →
Clientes** en el admin) y un artículo publicado por *otro* vendedor: nadie
puede comprar lo suyo.

| Método y ruta | Qué hace |
|---|---|
| `GET /api/pagos/metodos/` | Métodos disponibles. Con `?monto=` filtra los que aplican |
| `POST /api/pagos/` | Registra el pago. 201 aprobado o pendiente, 409 rechazado |
| `GET /api/pagos/` | Historial del cliente autenticado |
| `GET /api/pagos/<referencia>/` | Detalle de un pago propio |
| `POST /api/pagos/<referencia>/confirmar/` | Resuelve un pago pendiente (PSE, efectivo) |

La forma más rápida de recorrerla es el navegador: con la sesión iniciada,
<http://127.0.0.1:8000/api/pagos/metodos/> abre la interfaz navegable de DRF y
desde ahí se pueden enviar peticiones sin herramientas extra.

Por defecto la pasarela también corre en modo **MOCK**: aprueba las tarjetas,
deja pendientes PSE y efectivo, y rechaza cualquier pago cuyo token contenga
`RECHAZAR`, útil para demostrar los tres caminos sin salir a internet.

```bash
curl -u usuario:clave -X POST http://127.0.0.1:8000/api/pagos/ \
  -H "Content-Type: application/json" \
  -d '{"metodo_pago":"TARJETA_CREDITO","carro":1,"cuotas":12,"token_tarjeta":"tok_prueba"}'
```

Detalles de diseño, diagrama de secuencia y contrato completo en
[docs/pagos.md](docs/pagos.md).

## API Flask de cuentas y administración

Nginx envía `/api/v2/` y `/admin/v2/` al servicio Flask de cuentas. La API
incluye login, registro, cierre de sesión y consulta de la sesión actual.
`GET /api/v2/vendedores/`, `/clientes/`, `/carros/`, `/usuarios/` y `/grupos/`
exponen los registros administrativos; cada recurso admite operaciones CRUD.
Los cambios requieren sesión autenticada como staff y token CSRF: primero
consulta `GET /api/v2/csrf/`, o usa el `csrf_token` devuelto por login/registro,
y envíalo como `X-CSRFToken`.

El panel Flask está disponible en `/admin/v2/` e incluye las entidades
administradas por CarFit. La bitácora de transacciones es de solo lectura;
los pagos permiten editar los mismos campos que deja editables el admin
actual, pero no crear pagos desde el panel.
Las páginas web de inicio, registro y login siguen en Django; también se
conserva la API Django bajo `/api/v1/` y el panel original `/admin/`. Flask
comparte con Django la base de datos y las sesiones, por lo que la cookie
autenticada funciona en ambas aplicaciones.


## Pruebas

```bash
python manage.py test marketplace
```
