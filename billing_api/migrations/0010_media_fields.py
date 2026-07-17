from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0009_tenant_provision_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="logo_url",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
