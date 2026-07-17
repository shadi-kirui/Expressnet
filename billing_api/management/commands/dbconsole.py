from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


META_COMMANDS = {
    ".exit",
    ".help",
    ".models",
    ".quit",
    ".schema",
    ".tables",
    "exit",
    "help",
    "models",
    "quit",
    "schema",
    "tables",
}


class Command(BaseCommand):
    help = "Open a lightweight SQL console using Django's configured database connection."

    def add_arguments(self, parser):
        parser.add_argument(
            "-c",
            "--execute",
            help="Run a single SQL statement or console meta command, then exit.",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(
                f"Connected to {connection.vendor} database alias 'default'."
            )
        )

        if options["execute"]:
            self.run_input(options["execute"])
            return

        self.stdout.write("Type .help for commands. End SQL statements with ;")
        buffer = []
        while True:
            try:
                prompt = "db> " if not buffer else "... "
                line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("")
                break

            if not line:
                continue

            command_name = line.split()[0].lower()
            if not buffer and command_name in META_COMMANDS:
                try:
                    should_continue = self.run_meta_command(line)
                except CommandError as exc:
                    self.stderr.write(self.style.ERROR(str(exc)))
                    continue
                if not should_continue:
                    break
                continue

            buffer.append(line)
            if line.endswith(";"):
                statement = " ".join(buffer).rstrip(";")
                buffer = []
                try:
                    self.run_sql(statement)
                except CommandError as exc:
                    self.stderr.write(self.style.ERROR(str(exc)))

    def run_input(self, value):
        command_name = value.strip().split()[0].lower()
        if command_name in META_COMMANDS:
            self.run_meta_command(value.strip())
        else:
            self.run_sql(value.strip().rstrip(";"))

    def run_meta_command(self, value):
        parts = value.split(maxsplit=1)
        command_name = parts[0].lower().lstrip(".")
        argument = parts[1].strip() if len(parts) > 1 else ""

        if command_name in {"exit", "quit"}:
            return False
        if command_name == "help":
            self.print_help()
            return True
        if command_name == "tables":
            self.print_tables()
            return True
        if command_name == "models":
            self.print_models()
            return True
        if command_name == "schema":
            if not argument:
                raise CommandError("Usage: .schema <table_name>")
            self.print_schema(argument)
            return True

        raise CommandError(f"Unknown command: {value}")

    def print_help(self):
        self.stdout.write(
            "\n".join(
                [
                    "Console commands:",
                    "  .tables             List database tables",
                    "  .schema <table>     Show columns for a table",
                    "  .models             List installed Django models",
                    "  .help               Show this help",
                    "  .exit / .quit       Close the console",
                    "",
                    "Run SQL by ending a statement with ;",
                    "Example: SELECT id, email FROM billing_api_user LIMIT 5;",
                ]
            )
        )

    def print_tables(self):
        tables = connection.introspection.table_names()
        self.print_rows([(table,) for table in tables], ["table"])

    def print_models(self):
        rows = [
            (model._meta.label, model._meta.db_table)
            for model in apps.get_models()
        ]
        self.print_rows(rows, ["model", "table"])

    def print_schema(self, table_name):
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table_name)
        rows = [
            (
                column.name,
                column.type_code,
                "yes" if column.null_ok else "no",
                column.default,
            )
            for column in description
        ]
        self.print_rows(rows, ["column", "type", "nullable", "default"])

    def run_sql(self, statement):
        if not statement:
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                if cursor.description:
                    columns = [column[0] for column in cursor.description]
                    self.print_rows(cursor.fetchall(), columns)
                else:
                    self.stdout.write(f"{cursor.rowcount} row(s) affected.")
        except Exception as exc:
            raise CommandError(str(exc)) from exc

    def print_rows(self, rows, columns):
        rows = list(rows)
        text_rows = [[self.format_value(value) for value in row] for row in rows]
        widths = [
            max(len(str(column)), *(len(row[index]) for row in text_rows))
            if text_rows
            else len(str(column))
            for index, column in enumerate(columns)
        ]

        header = " | ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns))
        separator = "-+-".join("-" * width for width in widths)
        self.stdout.write(header)
        self.stdout.write(separator)
        for row in text_rows:
            self.stdout.write(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        self.stdout.write(f"{len(rows)} row(s).")

    def format_value(self, value):
        if value is None:
            return "NULL"
        return str(value)
