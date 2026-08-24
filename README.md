**integrantes:**

Julian Jimenez Garcia

Simon Mazo Gomez

Alejandro Cifuentes Arroyave

# CarFit

Marketplace que **facilita y centraliza la compra y venta de repuestos y carros
en un solo lugar**, de manera fácil y adaptada a las necesidades de cada usuario.


## Arquitectura

La funcionalidad crítica refactorizada es **Crear Artículo** (publicación de un
vehículo por parte de un vendedor). Está organizada en capas, con las
dependencias apuntando siempre hacia el dominio:

```
marketplace/
├── views.py            # Capa de Interfaz:  CBV de 13 líneas, solo traduce HTTP
├── forms.py            #                     valida formato, no reglas de negocio
├── api/                # Capa de Presentación (DRF): APIView + Serializers
│   ├── serializers.py  #   validan formato, no reglas de negocio
│   ├── views.py        #   una APIView por recurso, sin lógica
│   ├── errores.py      #   traduce errores de dominio a códigos HTTP
│   └── urls.py
├── services.py         # Capa de Aplicación: orquesta los casos de uso
├── domain/             # Capa de Dominio:   reglas de negocio, sin Django ni HTTP
│   ├── builders.py     #   Patrón Builder (Fluent Interface)
│   ├── metodos_pago.py #   catálogo de métodos de pago y sus reglas
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

1. Entra a <http://127.0.0.1:8000/admin/> e inicia sesión con el superusuario
   que acabas de crear.
2. En **Marketplace → Vendedors**, crea un `Vendedor` asociado a ese mismo
   usuario (campo `usuario`); es obligatorio para poder publicar artículos.
3. Ve a <http://127.0.0.1:8000/articulos/nuevo/>. Si no habías iniciado sesión
   fuera del admin, te pedirá loguearte en <http://127.0.0.1:8000/cuentas/login/>
   con el mismo usuario.

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


## Pruebas

```bash
python manage.py test marketplace
```



