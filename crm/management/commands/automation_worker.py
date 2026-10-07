import logging, time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from crm.services import run_scheduled
logger=logging.getLogger(__name__)
class Command(BaseCommand):
    help='Worker persistente de automações; alternativa ao cron run_automations.'
    def add_arguments(self,parser): parser.add_argument('--interval',type=int,default=60)
    def handle(self,*args,**options):
        self.stdout.write('Worker de automações iniciado.')
        try:
            while True:
                close_old_connections()
                try: run_scheduled()
                except Exception: logger.exception('Falha ao processar automações; nova tentativa no próximo ciclo.')
                time.sleep(max(10,options['interval']))
        except KeyboardInterrupt: self.stdout.write('Worker encerrado.')
