from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import F, Q, Sum
from django.core.exceptions import ValidationError
from django.utils import timezone
from . import models as m
from .permissions import scope, MANAGERS

def audit(user,obj,action,before=None,after=None):
    m.AuditLog.objects.create(user=user if user and user.is_authenticated else None,entity=obj._meta.model_name,object_id=str(obj.pk),action=action,before=before or {},after=after or {})
def history(lead,user,text):
    if text.startswith('Aguardando distribuição:') and lead.history.order_by('-created_at').values_list('description',flat=True).first()==text: return
    m.History.objects.create(lead=lead,user=user,description=text,is_demo=lead.is_demo)
def company(): return m.Company.objects.first() or m.Company.objects.create()
def days(value): return sorted(set(int(x.strip()) for x in value.split(',') if x.strip().isdigit()))
def notify(user,title,link='',key=None):
    if not user: return
    if key: m.Notification.objects.get_or_create(key=key,defaults={'user':user,'title':title,'link':link})
    else: m.Notification.objects.create(user=user,title=title,link=link)
@transaction.atomic
def assign(lead,user=None,force=False):
    lead=m.Lead.objects.select_for_update().get(pk=lead.pk)
    if lead.owner and not force: return lead.owner
    c=company(); c=m.Company.objects.select_for_update().get(pk=c.pk)
    now=timezone.localtime()
    if c.restrict_hours and (str(now.weekday()) not in c.business_days.split(',') or not c.business_start<=now.time().replace(tzinfo=None)<c.business_end):
        history(lead,user,'Aguardando distribuição: fora do horário comercial.'); return None
    candidates=list(m.User.objects.filter(role='sdr',is_active=True,available=True).order_by('id'))
    for offset in range(len(candidates)):
        index=(c.round_robin_cursor+offset)%len(candidates)
        candidate=candidates[index]
        count=m.Lead.objects.filter(owner=candidate,stage__kind='open').exclude(pk=lead.pk).count()
        if count>=candidate.lead_limit: continue
        old=str(lead.owner or 'Sem responsável')
        lead.owner=lead.sdr=candidate; lead.save(update_fields=['owner','sdr','updated_at'])
        c.round_robin_cursor=(index+1)%len(candidates); c.save(update_fields=['round_robin_cursor','updated_at'])
        history(lead,user,f'Lead atribuído automaticamente para {candidate}.')
        audit(user,lead,'Distribuição',{'responsável':old},{'responsável':str(candidate)})
        notify(candidate,'Novo lead recebido',f'/leads/{lead.pk}/')
        return candidate
    history(lead,user,'Aguardando distribuição: nenhum SDR elegível.'); return None

def create_task(lead,title,due,kind='return',key=None,owner=None,customer=None):
    owner=owner or (lead.owner if lead else None)
    if not owner: return
    values={'title':title,'owner':owner,'lead':lead,'customer':customer or (lead.customer if lead else None),'due_at':due,'kind':kind,'is_demo':lead.is_demo if lead else False}
    if key: return m.Task.objects.get_or_create(automation_key=key,defaults=values)[0]
    return m.Task.objects.create(**values)
def automate(trigger,lead,user=None,sale=None):
    for rule in m.Automation.objects.filter(active=True,trigger=trigger):
        if rule.source_id and (not lead or rule.source_id!=lead.source_id): continue
        if rule.stage_id and (not lead or rule.stage_id!=lead.stage_id): continue
        if rule.action=='assign' and lead: assign(lead,user)
        elif rule.action=='task':
            stamp=str(sale.pk) if sale else str(lead.stage_changed_at) if lead else ''
            create_task(lead,rule.name,timezone.now()+timedelta(days=rule.delay_days),rule.task_kind,f'auto:{rule.pk}:{lead.pk if lead else sale.pk}:{stamp}',owner=sale.seller if sale else None,customer=sale.customer if sale else None)
@transaction.atomic
def create_lead(lead,user=None):
    if lead.owner and lead.owner.role_code=='sdr' and not lead.sdr: lead.sdr=lead.owner
    if lead.owner and lead.owner.role_code=='seller' and not lead.seller: lead.seller=lead.owner
    if lead.stage.qualifies_lead and not lead.qualified_at: lead.qualified_at=timezone.now()
    lead.full_clean(); lead.save()
    history(lead,user,'Lead criado.')
    if not lead.owner: assign(lead,user)
    else: notify(lead.owner,'Novo lead recebido',f'/leads/{lead.pk}/')
    lead.refresh_from_db(); automate('new_lead',lead,user)
    audit(user,lead,'Criação')
    return lead
@transaction.atomic
def change_stage(lead,stage,user,reason=None,followups=True):
    lead=m.Lead.objects.select_for_update().get(pk=lead.pk)
    if not scope(m.Lead,user).filter(pk=lead.pk).exists(): raise ValidationError('Lead fora do seu acesso.')
    if user.role_code=='sdr' and (not stage.allows_sdr or lead.stage.kind in {'won','after'}): raise ValidationError('SDR pode qualificar e transferir; negociação pertence ao vendedor.')
    if stage.kind in {'won','after'} and not m.Sale.objects.filter(lead=lead,status='confirmed').exists(): raise ValidationError('Registre uma venda antes de entrar nesta etapa.')
    if stage.kind=='lost' and not reason: raise ValidationError('Informe o motivo da perda.')
    if lead.stage_id==stage.pk: return lead
    old=lead.stage.name; lead.stage=stage; lead.loss_reason=reason if stage.kind=='lost' else None; lead.stage_changed_at=timezone.now()
    if stage.qualifies_lead and not lead.qualified_at: lead.qualified_at=timezone.now()
    lead.save()
    history(lead,user,f'Etapa alterada: {old} → {stage.name}'+(f'. Motivo: {reason}' if reason else '.'))
    audit(user,lead,'Mudança de etapa',{'etapa':old},{'etapa':stage.name,'motivo':str(reason or '')})
    if stage.behavior=='proposal' and followups: schedule_followups(lead)
    automate('stage',lead,user)
    return lead

def schedule_followups(lead,proposal=None):
    if not lead.owner: return
    base=proposal.created_at if proposal else timezone.now()
    key=str(proposal.pk) if proposal else f'{lead.pk}:{lead.stage_changed_at.isoformat()}'
    for day in days(company().followup_days):
        create_task(lead,f'Follow-up de proposta · {lead.customer} ({day}d)',base+timedelta(days=day),'return',f'followup:{key}:{day}')
    sequence=days(company().followup_days)
    if sequence: create_task(lead,f'Reativar · {lead.customer}',base+timedelta(days=max(sequence)+1),'reactivate',f'reactivate:{key}')
    lead.next_followup=base+timedelta(days=min(sequence or [1])); lead.save(update_fields=['next_followup','updated_at'])
@transaction.atomic
def record_activity(activity,user):
    activity.user=user; activity.full_clean(); activity.save()
    if activity.lead:
        lead=m.Lead.objects.select_for_update().get(pk=activity.lead_id)
        lead.last_interaction=activity.occurred_at
        if activity.kind!='note' and not lead.first_contact_at: lead.first_contact_at=activity.occurred_at
        rule=m.ScoringRule.objects.filter(kind=activity.kind).first()
        lead.score=min(100,lead.score+(rule.points if rule else 0)); lead.save()
        history(lead,user,activity.get_kind_display()+': '+activity.description)
    audit(user,activity,'Interação registrada')
@transaction.atomic
def move_stock(variant,kind,quantity,user,reason,sale=None):
    if quantity<1: raise ValidationError('Quantidade deve ser positiva.')
    inv,_=m.Inventory.objects.get_or_create(variant=variant)
    inv=m.Inventory.objects.select_for_update().get(pk=inv.pk)
    if kind in {'out','reserve'} and inv.available<quantity: raise ValidationError(f'Estoque insuficiente para {variant}. Disponível: {inv.available}.')
    if kind=='in': inv.quantity+=quantity
    elif kind=='out': inv.quantity-=quantity
    elif kind=='reserve': inv.reserved+=quantity
    elif kind=='release':
        if quantity>inv.reserved: raise ValidationError('Reserva insuficiente.')
        inv.reserved-=quantity
    else: raise ValidationError('Movimento inválido.')
    if variant.imei and inv.quantity>1: raise ValidationError('Aparelho com IMEI individual não pode ter estoque maior que 1.')
    inv.full_clean(); inv.save()
    obj=m.InventoryMovement.objects.create(variant=variant,kind=kind,quantity=quantity,user=user,reason=reason,sale=sale)
    audit(user,obj,'Movimento de estoque',after={'tipo':kind,'quantidade':quantity})
    if inv.available<=inv.minimum:
        for manager in m.User.objects.filter(role__in=MANAGERS,is_active=True): notify(manager,f'Estoque baixo: {variant}','/inventory/')
    return obj

def validate_quote(proposal,items):
    if not items: raise ValidationError('Inclua pelo menos um produto.')
    total=sum((i.quantity*i.unit_price for i in items),Decimal(0))-proposal.discount
    if total<0: raise ValidationError('Desconto excede o valor dos itens.')
    trade=proposal.trade.entry_value if proposal.trade else Decimal(0)
    if proposal.down_payment+trade>total: raise ValidationError('Entrada e troca excedem o valor final.')
    if proposal.trade and proposal.trade.customer_id!=proposal.customer_id: raise ValidationError('A troca deve pertencer ao cliente.')
    if proposal.lead and proposal.lead.customer_id!=proposal.customer_id: raise ValidationError('O lead deve pertencer ao cliente.')
    return total
@transaction.atomic
def send_proposal(proposal,user):
    proposal=m.Proposal.objects.select_for_update().get(pk=proposal.pk)
    validate_quote(proposal,list(proposal.items.all()))
    if proposal.valid_until<timezone.localdate(): raise ValidationError('Proposta vencida.')
    if proposal.status not in {'draft','negotiating','sent'}: raise ValidationError('Status não permite envio.')
    proposal.status='sent'; proposal.save()
    if proposal.lead:
        stage=m.Stage.objects.filter(behavior='proposal').first()
        if stage: change_stage(proposal.lead,stage,user,followups=False)
        schedule_followups(proposal.lead,proposal)
        history(proposal.lead,user,f'Proposta gerada para envio: {proposal}. Entrega externa não confirmada.')
    audit(user,proposal,'Proposta preparada para envio')
@transaction.atomic
def confirm_sale(proposal,user):
    proposal=m.Proposal.objects.select_for_update(of=('self',)).select_related('customer','seller','lead','trade').get(pk=proposal.pk)
    if m.Sale.objects.filter(proposal=proposal).exists(): raise ValidationError('Esta proposta já foi convertida em venda.')
    if proposal.status in {'refused','expired'} or proposal.valid_until<timezone.localdate(): raise ValidationError('Proposta recusada ou expirada.')
    items=list(proposal.items.select_related('variant__product').order_by('variant_id'))
    total=validate_quote(proposal,items)
    if proposal.trade and m.Sale.objects.filter(trade=proposal.trade).exists(): raise ValidationError('Aparelho de troca já utilizado.')
    cost=sum((i.quantity*i.variant.cost for i in items),Decimal(0))
    sale=m.Sale.objects.create(customer=proposal.customer,lead=proposal.lead,proposal=proposal,seller=proposal.seller,discount=proposal.discount,down_payment=proposal.down_payment,trade=proposal.trade,installments=proposal.installments,payment_method=proposal.payment_method,total=total,cost=cost,notes=proposal.notes,is_demo=proposal.is_demo)
    commission=Decimal(0)
    subtotal=sum((i.quantity*i.unit_price for i in items),Decimal(0))
    for item in items:
        move_stock(item.variant,'out',item.quantity,user,f'Venda {str(sale.pk)[:8]}',sale)
        m.SaleItem.objects.create(sale=sale,variant=item.variant,quantity=item.quantity,unit_price=item.unit_price,unit_cost=item.variant.cost,is_demo=sale.is_demo)
        rules=m.CommissionRule.objects.filter(active=True).filter(Q(product=item.variant.product)|Q(product__isnull=True,category=item.variant.product.category)|Q(product__isnull=True,category='')).order_by('-product_id','-category','created_at')
        rule=max(rules,key=lambda r: (bool(r.product_id),bool(r.category),str(r.created_at)),default=None)
        net=(item.quantity*item.unit_price)*(total/subtotal if subtotal else 0)
        if rule: commission+=net*rule.percent/100+item.quantity*rule.fixed
        elif item.variant.commission_fixed is not None: commission+=item.quantity*item.variant.commission_fixed
        else: commission+=net*proposal.seller.commission_percent/100
    m.Commission.objects.create(sale=sale,user=sale.seller,amount=commission.quantize(Decimal('.01'),rounding=ROUND_HALF_UP),is_demo=sale.is_demo)
    if proposal.trade:
        device=m.UsedDevice.objects.select_for_update().get(pk=proposal.trade_id)
        if device.status!='evaluated': raise ValidationError('Aparelho de troca já recebido.')
        existing=m.Variant.objects.filter(imei=device.imei).first()
        if existing and (device.stock_variant_id!=existing.pk or existing.inventory.quantity!=0): raise ValidationError('IMEI já cadastrado em estoque.')
        product,_=m.Product.objects.get_or_create(name=device.model,brand=device.brand,defaults={'model':device.model})
        used=existing or m.Variant.objects.create(product=product,capacity=device.capacity,color=device.color,condition='used',imei=device.imei,price=device.resale_price,cost=device.total_cost,is_demo=sale.is_demo)
        move_stock(used,'in',1,user,'Aparelho recebido na troca',sale)
        device.stock_variant=used; device.status='received'; device.save()
    cash_total=total-(proposal.trade.entry_value if proposal.trade else 0)
    if proposal.down_payment:
        m.Payment.objects.create(sale=sale,amount=proposal.down_payment,method=proposal.payment_method,is_demo=sale.is_demo)
    balance=cash_total-proposal.down_payment
    if balance:
        part=(balance/proposal.installments).quantize(Decimal('.01'))
        for n in range(proposal.installments):
            amount=part if n<proposal.installments-1 else balance-part*(proposal.installments-1)
            m.Payment.objects.create(sale=sale,amount=amount,method=proposal.payment_method,due_at=timezone.localdate()+timedelta(days=30*n),is_demo=sale.is_demo)
    proposal.status='accepted'; proposal.save()
    if sale.lead:
        commercial_lead=m.Lead.objects.select_for_update().get(pk=sale.lead_id)
        if commercial_lead.owner_id!=sale.seller_id or commercial_lead.seller_id!=sale.seller_id:
            previous=str(commercial_lead.owner or 'Sem responsável'); commercial_lead.owner=commercial_lead.seller=sale.seller; commercial_lead.save()
            history(commercial_lead,user,f'Responsável comercial definido na venda: {previous} → {sale.seller}.')
            audit(user,commercial_lead,'Responsável da venda',{'responsável':previous},{'responsável':str(sale.seller)})
        stage=m.Stage.objects.filter(kind='won').first()
        if stage: change_stage(sale.lead,stage,user)
        m.Task.objects.filter(lead=sale.lead,status='open',automation_key__startswith='followup:').update(status='cancelled')
        m.Task.objects.filter(lead=sale.lead,status='open',automation_key__startswith='reactivate:').update(status='cancelled')
        history(sale.lead,user,f'Venda registrada: R$ {total}. Pagamento aguardando confirmação.')
    after_user=m.User.objects.filter(role='after',is_active=True).first() or sale.seller
    labels=['Confirmar recebimento','Verificar satisfação','Solicitar avaliação','Relacionamento','Oportunidade de upgrade']
    for n,day in enumerate(days(company().aftersale_days)):
        create_task(sale.lead,f'{labels[min(n,4)]} · {sale.customer}',timezone.now()+timedelta(days=day),'review' if n==2 else 'after',f'after:{sale.pk}:{day}',owner=after_user,customer=sale.customer)
    automate('sale',sale.lead,user,sale)
    notify(sale.seller,'Venda registrada',f'/sales/{sale.pk}/')
    audit(user,sale,'Venda confirmada',after={'total':str(total)})
    return sale
@transaction.atomic
def cancel_sale(sale,user):
    sale=m.Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status!='confirmed': raise ValidationError('Venda já cancelada.')
    if sale.commission.status=='paid': raise ValidationError('Comissão paga exige estorno financeiro antes do cancelamento.')
    if sale.trade and sale.trade.stock_variant:
        move_stock(sale.trade.stock_variant,'out',1,user,'Devolução de aparelho de troca',sale)
        sale.trade.status='evaluated'; sale.trade.save()
        # Preserve the serialised device history; future receipt can reuse it after an explicit stock review.
    for item in sale.items.select_related('variant'): move_stock(item.variant,'in',item.quantity,user,'Cancelamento de venda',sale)
    sale.status='cancelled'; sale.save()
    sale.payments.update(status='cancelled'); m.Commission.objects.filter(sale=sale).update(status='cancelled')
    m.Task.objects.filter(automation_key__startswith=f'after:{sale.pk}:',status='open').update(status='cancelled')
    if sale.lead:
        if not m.Sale.objects.filter(lead=sale.lead,status='confirmed').exists():
            stage=m.Stage.objects.filter(behavior='negotiation').first()
            if stage: change_stage(sale.lead,stage,user)
        history(sale.lead,user,'Venda cancelada; estoque reposto.')
    audit(user,sale,'Venda cancelada')
@transaction.atomic
def anonymize(customer,user):
    before={'anonimizado':bool(customer.anonymized_at)}
    customer.first_name='Cliente anonimizado'; customer.last_name=''; customer.phone=''; customer.whatsapp=''; customer.instagram=''; customer.email=''; customer.city=''; customer.state=''; customer.birthday=None; customer.notes=''; customer.consent=False; customer.consent_at=None; customer.anonymized_at=timezone.now(); customer.save()
    m.Lead.objects.filter(customer=customer).update(notes='',ad='',utm_source='',utm_medium='',utm_campaign='',utm_content='',utm_term='')
    m.Activity.objects.filter(customer=customer).update(description='Conteúdo removido por anonimização')
    m.Message.objects.filter(conversation__customer=customer).update(body='Conteúdo removido por anonimização')
    m.Task.objects.filter(customer=customer).update(title='Tarefa de cliente anonimizado',description='')
    for device in m.UsedDevice.objects.filter(customer=customer):
        if device.photo: device.photo.delete(save=True)
        for photo in device.photos.all(): photo.image.delete(save=False); photo.delete()
    m.UsedDevice.objects.filter(customer=customer).update(notes='',accessories='')
    m.Proposal.objects.filter(customer=customer).update(notes='')
    m.Sale.objects.filter(customer=customer).update(notes='')
    m.History.objects.filter(lead__customer=customer).update(description='Evento comercial preservado; conteúdo pessoal removido')
    # Redact snapshots that could contain personal data, retaining actor/date/action.
    ids=[str(customer.pk)]+[str(x) for x in customer.leads.values_list('pk',flat=True)]
    for model in [m.Activity,m.Task,m.UsedDevice,m.Proposal,m.Sale,m.Conversation]:
        ids += [str(x) for x in model.objects.filter(customer=customer).values_list('pk',flat=True)]
    ids += [str(x) for x in m.Message.objects.filter(conversation__customer=customer).values_list('pk',flat=True)]
    m.AuditLog.objects.filter(object_id__in=ids).update(before={},after={})
    audit(user,customer,'Anonimização LGPD',before,{'anonimizado':True})

def run_scheduled():
    for lead in m.Lead.objects.filter(owner__isnull=True,stage__kind='open'): assign(lead)
    for proposal in m.Proposal.objects.filter(valid_until__lt=timezone.localdate(),status__in=['draft','sent','viewed','negotiating']):
        with transaction.atomic():
            proposal=m.Proposal.objects.select_for_update().get(pk=proposal.pk)
            if proposal.status not in {'draft','sent','viewed','negotiating'}: continue
            before=proposal.status; proposal.status='expired'; proposal.save()
            audit(None,proposal,'Expiração automática',{'status':before},{'status':'expired'})
            if proposal.lead: history(proposal.lead,None,'Proposta expirada automaticamente.')
    for task in m.Task.objects.filter(status='open',due_at__lt=timezone.now()).select_related('owner'):
        notify(task.owner,'Tarefa atrasada: '+task.title,f'/tasks/{task.pk}/',f'overdue:{task.pk}')
    cutoff=timezone.now()-timedelta(minutes=company().sla_minutes)
    for lead in m.Lead.objects.filter(first_contact_at__isnull=True,created_at__lt=cutoff,stage__kind='open',owner__isnull=False):
        notify(lead.owner,f'SLA estourado: {lead.customer}',f'/leads/{lead.pk}/',f'sla:{lead.pk}')

    for goal in m.Goal.objects.filter(start__lte=timezone.localdate(),end__gte=timezone.localdate()):
        from .metrics import goal_value
        if goal.target and goal_value(goal)>=goal.target:
            recipients=m.User.objects.filter(pk=goal.user_id) if goal.user_id else m.User.objects.filter(team_id=goal.team_id,is_active=True) if goal.team_id else m.User.objects.filter(role__in=MANAGERS,is_active=True)
            for user in recipients: notify(user,'Meta atingida: '+goal.name,f'/goals/{goal.pk}/',f'goal:{goal.pk}:{user.pk}')
