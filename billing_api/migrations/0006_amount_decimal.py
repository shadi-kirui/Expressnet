from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0005_fix_timestamps"),
    ]

    operations = [
        migrations.AlterField(
            "payment",
            "amount",
            models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
    ]
