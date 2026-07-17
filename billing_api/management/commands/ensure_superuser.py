import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a Django superuser from environment variables."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.getenv("DJANGO_SUPERUSER_EMAIL"))
        parser.add_argument("--password", default=os.getenv("DJANGO_SUPERUSER_PASSWORD"))
        parser.add_argument("--name", default=os.getenv("DJANGO_SUPERUSER_NAME", "Super Admin"))

    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        password = options["password"]
        name = (options["name"] or "Super Admin").strip()

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping superuser creation. Set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD to enable it."
                )
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": name,
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        user.name = user.name or name
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} superuser {email}"))
