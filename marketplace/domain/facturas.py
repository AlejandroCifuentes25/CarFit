"""Generación de la factura de un pago.

Corresponde al método `Generar_Factura()` de `Pago` en el diagrama de
clases. Se modela como una función de dominio que produce un objeto de
valor inmutable, y no como un método del modelo `Pago`, para no mezclar
persistencia con una regla de negocio ("solo se factura lo que ya se
cobró") ni con el formato de salida (JSON en la API, HTML imprimible en la
web).
"""

from dataclasses import dataclass
from datetime import datetime

from ..models import Pago
from .exceptions import PagoNoFacturableError

#: Prefijo de los números de factura, distinto del de las referencias de
#: pago (`CF-`) para que ambos documentos no se confundan en un reclamo.
PREFIJO_FACTURA = "FAC"


@dataclass(frozen=True)
class Factura:
    """Comprobante de un pago aprobado. Solo lectura, no se persiste aparte.

    Se reconstruye a partir del `Pago` cada vez que se pide: como el pago no
    cambia una vez aprobado, no hay necesidad de guardar la factura como una
    entidad independiente ni de mantenerla sincronizada con nada.
    """

    numero: str
    fecha_emision: datetime
    referencia_pago: str
    cliente_nombre: str
    cliente_correo: str
    vendedor_nombre: str
    articulo_descripcion: str
    metodo_pago: str
    subtotal: int
    comision: int
    total: int
    moneda: str
    cuotas: int
    codigo_autorizacion: str


def generar_factura(pago: Pago) -> Factura:
    """Genera la factura de `pago`.

    Solo un pago `APROBADO` es facturable: facturar uno `PENDIENTE` cobraría
    algo que el banco todavía no confirmó, y uno `RECHAZADO` no debería
    tener factura porque no hubo cobro.

    Raises:
        PagoNoFacturableError: el pago no está en estado APROBADO.
    """
    if pago.estado != Pago.Estado.APROBADO:
        raise PagoNoFacturableError(pago.referencia, pago.estado)

    articulo = pago.carro or pago.repuesto
    vendedor = getattr(articulo, "vendedor", None)

    return Factura(
        numero=f"{PREFIJO_FACTURA}-{pago.referencia}",
        fecha_emision=pago.actualizado_en,
        referencia_pago=pago.referencia,
        cliente_nombre=pago.cliente.nombre,
        cliente_correo=pago.cliente.correo,
        vendedor_nombre=getattr(vendedor, "nombre", ""),
        articulo_descripcion=str(articulo) if articulo else "",
        metodo_pago=pago.get_metodo_pago_display(),
        subtotal=pago.precio,
        comision=pago.comision,
        total=pago.total,
        moneda=pago.moneda,
        cuotas=pago.cuotas,
        codigo_autorizacion=pago.codigo_autorizacion,
    )
