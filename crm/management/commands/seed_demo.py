from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from crm import models as m, services as s
class Command(BaseCommand):
    help='Cria dados fictícios identificados. Use somente em ambiente de demonstração.'
    def add_arguments(self,parser): parser.add_argument('--password',required=True)
    @transaction.atomic
    def handle(self,*args,**options):
        if m.User.objects.filter(is_demo=True).exists(): self.stdout.write('Demonstração já criada; dados preservados.'); return
        if m.Customer.objects.exists() or m.User.objects.exists(): raise CommandError('Demonstração somente em banco vazio; use um banco separado para preservar dados existentes.')
        call_command('init_crm')
        company=s.company(); company.name='iStore Premium · Demo'; company.is_demo=True; company.restrict_hours=False; company.save()
        team=m.Team.objects.create(name='Equipe Premium',is_demo=True)
        users={}
        for username,name,role in [('admin','Alex','admin'),('gestor','Daniel','manager'),('bruna','Bruna','sdr'),('mariaclara','Maria Clara','sdr'),('joao','João','seller'),('rafaela','Rafaela','seller'),('posvenda','Isabela','after')]:
            users[username]=m.User.objects.create_user(username=username,password=options['password'],first_name=name,last_name='Demo',role=role,team=team,is_demo=True)
        models=['iPhone 15','iPhone 15 Pro','iPhone 15 Pro Max','iPhone 16','iPhone 16 Pro','iPhone 16 Pro Max','iPhone 17','iPhone 17 Pro','iPhone 17 Pro Max','Galaxy S25 Ultra']
        variants=[]
        for i,name in enumerate(models):
            product=m.Product.objects.create(name=name,model=name,brand='Samsung' if i==9 else 'Apple',generation='2025' if i>=6 else '2024',supplier='Fornecedor demonstrativo',description='Produto fictício para demonstração do catálogo.',is_demo=True)
            variant=m.Variant.objects.create(product=product,capacity='256 GB' if i%2 else '128 GB',color=['Titânio natural','Preto','Azul'][i%3],price=Decimal(3990+i*650),cost=Decimal(2800+i*450),is_demo=True)
            m.Inventory.objects.create(variant=variant,quantity=18,minimum=3,is_demo=True)
            m.InventoryMovement.objects.create(variant=variant,user=users['admin'],kind='in',quantity=18,reason='Estoque inicial demonstrativo',is_demo=True)
            variants.append(variant)
        m.Inventory.objects.filter(variant=variants[-1]).update(quantity=2)
        campaign=m.Campaign.objects.create(name='Upgrade Premium · Outubro (demo)',source=m.Source.objects.get(name='Instagram'),investment=Decimal('1800'),is_demo=True)
        m.MarketingSpend.objects.create(campaign=campaign,amount=1800,date=timezone.localdate(),notes='Investimento fictício demonstrativo',is_demo=True)
        names=['Mariana Costa','Lucas Almeida','Beatriz Santos','Pedro Oliveira','Camila Rodrigues','Gabriel Silva','Fernanda Souza','Rafael Lima','Juliana Martins','André Pereira','Larissa Gomes','Matheus Ribeiro','Amanda Rocha','Thiago Carvalho','Isabela Mendes','Bruno Ferreira','Carolina Dias','Felipe Araújo','Natália Barbosa','Gustavo Moreira']
        customers=[]; now=timezone.now()
        for i,name in enumerate(names):
            first,last=name.split(' ',1)
            customers.append(m.Customer.objects.create(first_name=first,last_name=last,phone=f'1199900{i:04d}',whatsapp=f'1199900{i:04d}',email=f'cliente{i+1}@example.com',city=['São Paulo','Campinas','Santos'][i%3],state='SP',instagram=f'@cliente_demo_{i+1}',notes='Cliente fictício de demonstração.',consent=i%4!=0,consent_at=now if i%4!=0 else None,created_by=users['admin'],is_demo=True))
        leads=[]
        origins=['Instagram','WhatsApp','Tráfego pago','Indicação','Loja física']
        for i in range(30):
            source=m.Source.objects.get(name=origins[i%5]); stage=m.Stage.objects.get(position=i%8 if i<25 else 10)
            lead=m.Lead(customer=customers[i%20],source=source,stage=stage,product=variants[i%10].product,budget=variants[i%10].price,score=[20,50,85][i%3],campaign=campaign if source==campaign.source else None,desired_model=models[i%10],notes='Oportunidade fictícia para demonstração.',loss_reason=m.LossReason.objects.get(name=['Preço','Não respondeu','Produto indisponível'][i%3]) if i>=25 else None,is_demo=True)
            s.create_lead(lead,users['admin']); lead.refresh_from_db()
            if i<10: lead.seller=lead.owner=users['joao'] if i%2 else users['rafaela']
            created=now-timedelta(days=i%min(timezone.localdate().day,23),minutes=min(i*17,max(0,timezone.localtime().hour*60+timezone.localtime().minute-1)))
            lead.created_at=created; lead.stage_changed_at=created; lead.save()
            if i%4:
                activity=m.Activity(customer=lead.customer,lead=lead,kind=['whatsapp','price','availability'][i%3],description='Interação comercial fictícia, registrada manualmente para demonstração.',occurred_at=created+timedelta(minutes=2+i%7),is_demo=True)
                s.record_activity(activity,lead.owner or users['bruna'])
            leads.append(lead)
        trade=m.UsedDevice.objects.create(customer=customers[0],brand='Apple',model='iPhone 13',capacity='128 GB',color='Preto',imei='000000000000001',physical_state='Bom — aparelho demonstrativo',battery=86,appraisal=1800,entry_value=1600,repair_cost=150,resale_price=2300,is_demo=True)
        for i in range(20):
            lead=leads[i%20]; seller=users['joao'] if i%2 else users['rafaela']
            proposal=m.Proposal.objects.create(customer=lead.customer,lead=lead,seller=seller,valid_until=timezone.localdate()+timedelta(days=7),payment_method='pix' if i%2 else 'credit',installments=1 if i%2 else 3,notes='Proposta fictícia de demonstração.',is_demo=True)
            m.ProposalItem.objects.create(proposal=proposal,variant=variants[i%10],quantity=1,unit_price=variants[i%10].price,is_demo=True)
            if i<10:
                sale=s.confirm_sale(proposal,users['admin']); sale_time=now-timedelta(days=i%6)
                m.Sale.objects.filter(pk=sale.pk).update(created_at=sale_time)
                for payment in sale.payments.all(): payment.status='confirmed'; payment.confirmed_at=sale_time; payment.save()
                if i<3: m.Commission.objects.filter(sale=sale).update(status='paid' if i==0 else 'approved')
            else: s.send_proposal(proposal,users['admin'])
        # Include historical purchases for meaningful reactivation/upgrade demonstrations.
        historical=list(m.Sale.objects.order_by('created_at')[:2])
        for i,sale in enumerate(historical):
            historical_date=now-timedelta(days=420+180*i)
            m.Sale.objects.filter(pk=sale.pk).update(created_at=historical_date)
            if sale.lead: m.Lead.objects.filter(pk=sale.lead_id).update(created_at=historical_date-timedelta(days=2))
        for i in range(15):
            lead=leads[10+i]
            s.create_task(lead,['Retornar cliente','Confirmar disponibilidade','Agendar avaliação da troca'][i%3],now+timedelta(days=i%4-1,hours=i),'return',f'demo:task:{i}')
        for username in ['joao','rafaela']:
            m.Goal.objects.create(name=f'Meta mensal · {users[username].first_name}',user=users[username],kind='revenue',target=100000,start=timezone.localdate().replace(day=1),end=timezone.localdate()+timedelta(days=30),is_demo=True)
        m.Automation.objects.create(name='Instagram · Contato inicial',trigger='new_lead',source=m.Source.objects.get(name='Instagram'),action='task',delay_days=0,task_kind='whatsapp',is_demo=True)
        s.run_scheduled()
        self.stdout.write(self.style.SUCCESS('Demo criada: 20 clientes, 30 leads, 10 produtos, 20 propostas, 10 vendas e 7 usuários. Integrações desconectadas.'))
