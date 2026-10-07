from django.core.management.base import BaseCommand
from crm.services import run_scheduled
class Command(BaseCommand):
    help='Executa SLA, distribuição pendente, expiração e alertas idempotentes.'
    def handle(self,*args,**options):
        run_scheduled(); self.stdout.write(self.style.SUCCESS('Automações processadas.'))
