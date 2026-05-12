"""Migration inicial — crea la tabla `leads`."""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("email", models.EmailField(max_length=254, db_index=True)),
                ("nombre_contacto", models.CharField(max_length=120, blank=True, default="")),
                ("empresa", models.CharField(max_length=200)),
                ("nombre_fantasia", models.CharField(max_length=200, blank=True, default="")),
                ("rubro", models.CharField(
                    max_length=20, blank=True, default="",
                    choices=[
                        ("comercio", "Comercio / Retail"),
                        ("servicios", "Servicios profesionales"),
                        ("construccion", "Construcción"),
                        ("gastronomia", "Gastronomía / HoReCa"),
                        ("industria", "Industria / Manufactura"),
                        ("transporte", "Transporte y logística"),
                        ("tecnologia", "Tecnología / Software"),
                        ("salud", "Salud"),
                        ("educacion", "Educación"),
                        ("agricultura", "Agro / Pesca / Minería"),
                        ("inmobiliaria", "Inmobiliaria / Construcción"),
                        ("independiente", "Profesional independiente"),
                        ("otro", "Otro"),
                    ],
                )),
                ("rut_encrypted", models.BinaryField(blank=True, default=b"")),
                ("calculadora", models.CharField(
                    max_length=20,
                    choices=[
                        ("iva", "IVA"),
                        ("precio_venta", "Precio de venta"),
                        ("honorarios", "Honorarios"),
                        ("sueldo", "Sueldo líquido"),
                        ("cotizacion", "Cotización"),
                    ],
                )),
                ("accion", models.CharField(
                    max_length=10,
                    choices=[
                        ("descargar", "Descargar PDF"),
                        ("enviar", "Enviar por correo"),
                    ],
                )),
                ("acepto_politica", models.BooleanField(default=False)),
                ("acepto_marketing", models.BooleanField(default=False)),
                ("politica_version", models.CharField(max_length=10, default="2026-05")),
                ("ip_hash", models.CharField(max_length=64, blank=True, default="", db_index=True)),
                ("user_agent", models.CharField(max_length=300, blank=True, default="")),
                ("email_enviado", models.BooleanField(default=False)),
                ("email_error", models.CharField(max_length=200, blank=True, default="")),
            ],
            options={
                "db_table": "leads",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["email", "created_at"], name="leads_email_created_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["calculadora", "created_at"], name="leads_calc_created_idx"),
        ),
    ]
