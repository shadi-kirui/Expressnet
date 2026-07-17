import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0007_package_is_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("customer_id", models.CharField(blank=True, default="", max_length=80)),
                ("status", models.CharField(blank=True, default="open", max_length=50)),
                ("priority", models.CharField(blank=True, default="medium", max_length=50)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tickets", to="billing_api.tenant")),
            ],
        ),
    ]
