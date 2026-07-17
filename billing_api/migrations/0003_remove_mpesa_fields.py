from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0002_paystack_fields"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="mpesa_consumer_key"),
        migrations.RemoveField(model_name="tenant", name="mpesa_consumer_secret"),
        migrations.RemoveField(model_name="tenant", name="mpesa_shortcode"),
        migrations.RemoveField(model_name="tenant", name="mpesa_business_shortcode"),
        migrations.RemoveField(model_name="tenant", name="mpesa_shortcode_type"),
        migrations.RemoveField(model_name="tenant", name="mpesa_passkey"),
        migrations.RemoveField(model_name="tenant", name="mpesa_callback_base_url"),
        migrations.RemoveField(model_name="tenant", name="mpesa_callback_url"),
        migrations.RemoveField(model_name="tenant", name="mpesa_environment"),
        migrations.RemoveField(model_name="customer", name="last_mpesa_code"),
        migrations.RemoveField(model_name="payment", name="mpesa_code"),
    ]
