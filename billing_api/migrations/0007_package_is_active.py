from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0006_amount_decimal"),
    ]

    operations = [
        migrations.AddField(
            model_name="internetpackage",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
