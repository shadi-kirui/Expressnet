from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0008_ticket_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="provision_token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
