from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from dateutil.parser import parse

from nameparser import HumanName

from npl import models, utils

"""
    raw_date = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)

    raw_player = models.CharField(max_length=255, blank=True, null=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    cash_considerations = models.IntegerField(blank=True, null=True)

    raw_draft_pick = models.CharField(max_length=255, blank=True, null=True)
    # draft_pick = models.ForeignKey(DraftPick, on_delete=models.CASCADE)

    raw_team = models.CharField(max_length=255, blank=True, null=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team", null=True)

    raw_acquiring_team = models.CharField(max_length=255, blank=True, null=True)
    acquiring_team = models.ForeignKey(Team, on_delete=models.CASCADE, blank=True, null=True, related_name="acquiring_team")

    transaction_type = models.ForeignKey(TransactionType, on_delete=models.CASCADE, null=True)

    is_archive_transaction = models.BooleanField(default=False)

    notes = models.TextField(null=True, blank=True)
"""


class Command(BaseCommand):
    def handle(self, *args, **options):

        models.Transaction.objects.all().delete()
        models.TransactionType.objects.all().delete()

        transactions = utils.get_sheet(settings.LEAGUE_SHEET_ID, f"2025 Transactions!A:H", value_cutoff=None)[3:]

        for t in transactions:
            print(t)
            failed = False
            failed_text = ''

            t_obj = None
            tt_obj = None

            try:
                transaction_dict = {}
                transaction_dict['raw_date'] = t[0]
                transaction_dict['date'] = parse(t[0])
            except:
                failed = True
                failed_text = "no date"

            transaction_dict['raw_team'] = t[1]
            transaction_dict['raw_player'] = t[2]
            transaction_dict['mlb_id'] = None
            if len(t[4].strip()) > 5:
                transaction_dict['mlb_id'] = int(t[4].strip())
                if transaction_dict['mlb_id'] == "":
                    transaction_dict['mlb_id'] = None

            transaction_dict['raw_transaction_type'] = t[5]

            try:
                transaction_dict['raw_acquiring_team'] = t[6]
            except IndexError:
                pass

            try:
                transaction_dict['notes'] = t[7]
            except IndexError:
                pass

            transaction_dict['is_archive_transaction'] = True

            try:
                tt_obj = models.TransactionType.objects.get(transaction_type=t[5])

            except models.TransactionType.DoesNotExist:
                tt_obj = models.TransactionType(transaction_type=t[5])
                tt_obj.save()
                print(f"+ {tt_obj}")

            if not failed:                
                if transaction_dict['mlb_id']:
                    try:
                        t_obj = models.Transaction.objects.get(**transaction_dict)

                    except models.Transaction.DoesNotExist:
                        t_obj = models.Transaction(**transaction_dict)
                        t_obj.transaction_type = tt_obj
                        t_obj.save()
                        print(f"+ {t_obj}")
                
            else:
                print(f'failed: {failed_text}')
