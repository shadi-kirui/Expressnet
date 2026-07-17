from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="paystack_secret_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="tenant",
            name="paystack_subaccount_code",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="tenant",
            name="paystack_bearer",
            field=models.CharField(blank=True, default="subaccount", max_length=50),
        ),
        migrations.AddField(
            model_name="tenant",
            name="paystack_currency",
            field=models.CharField(blank=True, default="KES", max_length=10),
        ),
        migrations.AddField(
            model_name="customer",
            name="last_payment_code",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="payment_code",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="provider",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="currency",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_reference",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_access_code",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_authorization_url",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_customer_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_transaction_id",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_channel",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_paid_at",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="paystack_authorization_code",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
