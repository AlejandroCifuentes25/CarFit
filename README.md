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
├── views.py            # Capa de Interfaz   — CBV de 13 líneas, solo traduce HTTP
├── forms.py            #                     valida formato, no reglas de negocio
├── services.py         # Capa de Aplicación — orquesta el caso de uso
├── domain/             # Capa de Dominio    — reglas de negocio, sin Django ni HTTP
│   ├── builders.py     #   Patrón Builder (Fluent Interface)
│   ├── ports.py        #   Interfaces abstractas (Inversión de Dependencias)
│   └── exceptions.py
├── infra/              # Infraestructura    — detalles reemplazables
│   ├── factories.py    #   Patrón Factory (MOCK vs REAL por variable de entorno)
│   ├── validadores.py
│   └── notificadores.py
└── models.py           # Persistencia       — sin lógica de negocio
```


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
   usuario (campo `usuario`) — es obligatorio para poder publicar artículos.
3. Ve a <http://127.0.0.1:8000/articulos/nuevo/>. Si no habías iniciado sesión
   fuera del admin, te pedirá loguearte en <http://127.0.0.1:8000/cuentas/login/>
   con el mismo usuario.

Por defecto la app corre en modo **MOCK**: aprueba cualquier documento y
notifica por consola, sin necesidad de configurar nada. `.env.example` lista
las variables que se pueden **exportar en la terminal** para cambiar a modo
`REAL` (el proyecto no carga `.env` automáticamente, no existe `python-dotenv`
como dependencia — hay que exportarlas a mano si las quieres probar):

```bash
# PowerShell
$env:VALIDADOR_DOCUMENTAL = "REAL"
$env:NOTIFICADOR = "REAL"
python manage.py runserver
```

## Pruebas

```bash
python manage.py test marketplace
```



