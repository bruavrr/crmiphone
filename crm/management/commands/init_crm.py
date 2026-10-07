from django.core.management.base import BaseCommand
from crm import models as m
class Command(BaseCommand):
    help='Cria configurações iniciais idempotentes; não cria usuários ou dados demonstrativos.'
    def handle(self,*args,**options):
        if not m.Company.objects.exists(): m.Company.objects.create()
        for code,name in m.ROLES: m.Role.objects.get_or_create(code=code,defaults={'name':name})
        stages=['Novo lead','Primeiro contato','Em atendimento','Qualificado','Produto de interesse','Proposta enviada','Negociação','Aguardando pagamento','Venda realizada','Pós-venda','Perdido']
        colors=['#8c79dd','#95a9e7','#7db6ca','#72b3ab','#9cbf9c','#d9bb84','#daac87','#d7a2b5','#73bba2','#81abb1','#cb8c97']
        if not m.Stage.objects.exists():
            for i,name in enumerate(stages): m.Stage.objects.create(name=name,position=i,kind='won' if i==8 else 'after' if i==9 else 'lost' if i==10 else 'open',color=colors[i],behavior={0:'new',5:'proposal',6:'negotiation',7:'payment'}.get(i,'standard'),allows_sdr=i<=4 or i==10,qualifies_lead=3<=i<=9)
        for name in ['Instagram','Instagram Direct','WhatsApp','Facebook','Google','Tráfego pago','Formulário','Landing page','Indicação','Cliente antigo','Orgânico','Loja física','Evento','Outros']: m.Source.objects.get_or_create(name=name)
        for name in ['Preço','Comprou com concorrente','Sem dinheiro','Não respondeu','Desistiu','Produto indisponível','Forma de pagamento','Prazo','Outro']: m.LossReason.objects.get_or_create(name=name)
        for kind,points in [('whatsapp',10),('price',20),('availability',30),('payment',40),('purchase',50)]: m.ScoringRule.objects.get_or_create(kind=kind,defaults={'points':points})
        for channel in ['whatsapp','instagram','ai']: m.Integration.objects.get_or_create(channel=channel)
        self.stdout.write(self.style.SUCCESS('Configurações iniciais prontas.'))
