"""Dry-run proposals by default; apply requires explicit IDs, owner and feature flag."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from portal.models import Subscription
from portal.renewals import agreement, generate_invoice, review


class Command(BaseCommand):
    help = "Review renewal invoices without writes; --apply requires explicit subscriptions and administrator."

    def add_arguments(self, parser):
        parser.add_argument("--subscription", action="append", type=int, dest="ids")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parser.add_argument("--actor", help="Username of the active administrator authorizing the reviewed batch.")

    def handle(self, *args, **options):
        actor = None
        if options["apply"]:
            if not options["ids"] or not options["actor"]:
                raise CommandError("Apply requires explicit --subscription IDs and --actor.")
            actor = get_user_model().objects.filter(username=options["actor"], is_active=True,
                                                    is_staff=True, is_superuser=True).first()
            if actor is None:
                raise CommandError("Actor must be an active administrator.")
        subscriptions = Subscription.objects.select_related("order").order_by("next_billing_date", "pk")
        if options["ids"]:
            subscriptions = subscriptions.filter(pk__in=options["ids"])
            if subscriptions.count() != len(set(options["ids"])):
                raise CommandError("One or more subscriptions do not exist.")
        failures = False
        for subscription in subscriptions.iterator(chunk_size=100):
            try:
                proposal = review(subscription)
                if options["apply"]:
                    invoice, created = generate_invoice(subscription.pk, actor=actor,
                        expected_due=subscription.next_billing_date, expected_agreement=agreement(subscription))
                    message = ("Created " if created else "Existing ") + invoice.invoice_number
                else:
                    message = proposal["reason"]
                    if proposal["eligible"]:
                        message += (f" {proposal['currency']} {proposal['amount']}; "
                                    f"due {proposal['due'].isoformat()}; period ends {proposal['end'].isoformat()}.")
                self.stdout.write(f"Subscription {subscription.pk}: {message}")
            except (ValidationError, PermissionDenied) as error:
                failures = True
                self.stderr.write(f"Subscription {subscription.pk}: {error}")
        if failures:
            raise CommandError("Some subscriptions need review; inspect the per-subscription results before retrying.")
        if not options["apply"]:
            self.stdout.write("Dry run: no invoices or service changes made.")
