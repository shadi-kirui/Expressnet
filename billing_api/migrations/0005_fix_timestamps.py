from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing_api", "0004_user_adminuser_user_tenant_owner"),
    ]

    operations = [
        migrations.AlterField("tenant", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("tenant", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.AlterField("internetpackage", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("internetpackage", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.AlterField("customer", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("customer", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.AlterField("adminauditlog", "timestamp", models.DateTimeField(auto_now_add=True)),
    ]
