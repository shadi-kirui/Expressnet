from django.db import migrations, models
import secrets as crypto_secrets


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0011_tenant_subscription"),
    ]

    operations = [
        # Add radius_enabled to Tenant
        migrations.AddField(
            model_name="tenant",
            name="radius_enabled",
            field=models.BooleanField(default=False),
        ),
        # Add radius_secret to Customer
        migrations.AddField(
            model_name="customer",
            name="radius_secret",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        # Create RadiusNasClient table
        migrations.CreateModel(
            name="RadiusNasClient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nas_ip", models.GenericIPAddressField()),
                ("shared_secret", models.CharField(max_length=128)),
                ("identifier", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=models.CASCADE, related_name="nas_clients", to="billing_api.tenant")),
            ],
            options={
                "verbose_name": "RADIUS NAS Client",
                "verbose_name_plural": "RADIUS NAS Clients",
            },
        ),
        # Create RadiusSession table
        migrations.CreateModel(
            name="RadiusSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("acct_session_id", models.CharField(db_index=True, max_length=64)),
                ("nas_ip", models.GenericIPAddressField()),
                ("framed_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("service_type", models.CharField(blank=True, default="", max_length=16)),
                ("started_at", models.DateTimeField()),
                ("last_interim_at", models.DateTimeField(blank=True, null=True)),
                ("stopped_at", models.DateTimeField(blank=True, null=True)),
                ("input_octets", models.BigIntegerField(default=0)),
                ("output_octets", models.BigIntegerField(default=0)),
                ("terminate_cause", models.CharField(blank=True, default="", max_length=64)),
                ("tenant", models.ForeignKey(on_delete=models.CASCADE, to="billing_api.tenant")),
                ("customer", models.ForeignKey(on_delete=models.CASCADE, related_name="radius_sessions", to="billing_api.customer")),
            ],
            options={
                "ordering": ["-started_at"],
                "verbose_name": "RADIUS Session",
                "verbose_name_plural": "RADIUS Sessions",
            },
        ),
        # Add unique constraint for NAS client
        migrations.AddConstraint(
            model_name="radiusnasclient",
            constraint=models.UniqueConstraint(fields=("tenant", "nas_ip"), name="unique_nas_client_per_tenant"),
        ),
    ]