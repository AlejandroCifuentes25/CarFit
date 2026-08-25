"""Módulo de pagos: enriquece `Pago` y agrega la bitácora de transacciones.

El `Pago` original solo guardaba precio, método y estado como texto libre.
Esta migración le da vocabulario cerrado (choices), la referencia única que
sostiene la idempotencia y los importes que calcula el dominio.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pago',
            options={'ordering': ['-fecha']},
        ),
        migrations.AddField(
            model_name='pago',
            name='referencia',
            field=models.CharField(default='', max_length=60, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pago',
            name='repuesto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='pagos',
                to='marketplace.repuesto',
            ),
        ),
        migrations.AddField(
            model_name='pago',
            name='comision',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='total',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='moneda',
            field=models.CharField(default='COP', max_length=3),
        ),
        migrations.AddField(
            model_name='pago',
            name='cuotas',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='pago',
            name='pasarela',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='pago',
            name='referencia_pasarela',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='pago',
            name='codigo_autorizacion',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='pago',
            name='mensaje',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='pago',
            name='actualizado_en',
            field=models.DateTimeField(
                auto_now=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='pago',
            name='metodo_pago',
            field=models.CharField(
                choices=[
                    ('TARJETA_CREDITO', 'Tarjeta de crédito'),
                    ('TARJETA_DEBITO', 'Tarjeta débito'),
                    ('PSE', 'PSE (débito desde cuenta bancaria)'),
                    ('BILLETERA_DIGITAL', 'Billetera digital'),
                    ('EFECTIVO', 'Efectivo en corresponsal'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='pago',
            name='estado',
            field=models.CharField(
                choices=[
                    ('PENDIENTE', 'Pendiente de confirmación'),
                    ('APROBADO', 'Aprobado'),
                    ('RECHAZADO', 'Rechazado'),
                    ('ANULADO', 'Anulado'),
                    ('REEMBOLSADO', 'Reembolsado'),
                ],
                default='PENDIENTE',
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='pago',
            index=models.Index(
                fields=['cliente', 'estado'], name='pago_cliente_estado_idx'
            ),
        ),
        migrations.CreateModel(
            name='TransaccionPago',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'operacion',
                    models.CharField(
                        choices=[
                            ('PROCESAR', 'Procesar'),
                            ('CONSULTAR', 'Consultar'),
                            ('CONFIRMAR', 'Confirmar'),
                        ],
                        max_length=20,
                    ),
                ),
                ('pasarela', models.CharField(max_length=40)),
                (
                    'estado_resultante',
                    models.CharField(
                        choices=[
                            ('PENDIENTE', 'Pendiente de confirmación'),
                            ('APROBADO', 'Aprobado'),
                            ('RECHAZADO', 'Rechazado'),
                            ('ANULADO', 'Anulado'),
                            ('REEMBOLSADO', 'Reembolsado'),
                        ],
                        max_length=20,
                    ),
                ),
                ('codigo_autorizacion', models.CharField(blank=True, max_length=60)),
                ('mensaje', models.CharField(blank=True, max_length=200)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                (
                    'pago',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='transacciones',
                        to='marketplace.pago',
                    ),
                ),
            ],
            options={
                'ordering': ['creado_en'],
            },
        ),
    ]
