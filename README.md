**integrantes:**

Julian Jimenez Garcia

Simon Mazo 

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
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Luego entra a <http://127.0.0.1:8000/articulos/nuevo/>. Necesitas un `Vendedor`
asociado a tu usuario: créalo desde <http://127.0.0.1:8000/admin/>.

## Pruebas

```bash
python manage.py test marketplace
```



