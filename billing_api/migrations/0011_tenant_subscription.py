import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0010_media_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("basic", "Basic"), ("pro", "Pro"), ("enterprise", "Enterprise")], default="basic", max_length=50)),
                ("amount", models.DecimalField(decimal_places=2, default=1500, max_digits=10)),
                ("currency", models.CharField(default="KES", max_length=10)),
                ("billing_cycle_days", models.IntegerField(default=30)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_paid_at", models.DateTimeField(blank=True, null=True)),
                ("grace_period_days", models.IntegerField(default=3)),
                ("auto_renew", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="billing_api.tenant")),
            ],
        ),
        migrations.CreateModel(
            name="SubscriptionPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="KES", max_length=10)),
                ("paid_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("method", models.CharField(blank=True, default="manual", max_length=80)),
                ("reference", models.CharField(blank=True, default="", max_length=255)),
                ("period_start", models.DateTimeField(blank=True, null=True)),
                ("period_end", models.DateTimeField(blank=True, null=True)),
                ("recorded_by", models.CharField(blank=True, default="", max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="billing_api.tenantsubscription")),
            ],
        ),
    ]
