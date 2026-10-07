from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Avg, Q, Min
from django.db.models.functions import TruncDate
from django.utils import timezone
from . import models as m
from .permissions import scope, MANAGERS

def period(params):
    today=timezone.localdate(); choice=params.get('period','month'); start=today.replace(day=1); end=today
    if choice=='today': start=today
    elif choice=='yesterday': start=end=today-timedelta(days=1)
    elif choice=='7': start=today-timedelta(days=6)
    elif choice=='30': start=today-timedelta(days=29)
    elif choice=='previous': end=today.replace(day=1)-timedelta(days=1); start=end.replace(day=1)
    elif choice=='custom':
        from datetime import date
        try: start=date.fromisoformat(params['start']); end=date.fromisoformat(params['end'])
        except (ValueError,KeyError): pass
    if end<start: end=start
    return start,end

def metrics(user,params):
    start,end=period(params)
    leads=scope(m.Lead,user).filter(created_at__date__range=(start,end))
    sales=scope(m.Sale,user).filter(created_at__date__range=(start,end),status='confirmed')
    if params.get('owner'): leads=leads.filter(owner_id=params['owner']); sales=sales.filter(seller_id=params['owner'])
    if params.get('source'): leads=leads.filter(source_id=params['source']); sales=sales.filter(lead__source_id=params['source'])
    count=leads.count(); sale_count=sales.count(); revenue=sales.aggregate(n=Sum('total'))['n'] or Decimal(0)
    won=leads.filter(sale__status='confirmed').distinct().count()
    contacts=leads.filter(first_contact_at__isnull=False).count()
    qualified=leads.filter(qualified_at__isnull=False).count()
    proposals=scope(m.Proposal,user).filter(created_at__date__range=(start,end))
    rate=lambda n,d:round(100*n/d,1) if d else 0
    pct=lambda n,d: f'{rate(n,d)}%' if d else 'Dados insuficientes'
    cards=[('Leads recebidos',count,'No período','violet'),('Em atendimento',leads.filter(stage__kind='open',first_contact_at__isnull=False).count(),'Leads ativos','blue'),('Sem contato',leads.filter(first_contact_at__isnull=True,stage__kind='open').count(),'Precisam de atenção','orange'),('Conversão',pct(won,count),'Vendas da coorte de leads','green')]
    if user.role_code in MANAGERS or user.role_code=='seller':
        cards=[('Faturamento',f'R$ {revenue:,.2f}'.replace(',','X').replace('.',',').replace('X','.'),f'{sale_count} vendas no período','violet'),('Novos leads',count,'Recebidos no período','blue'),('Taxa de conversão',pct(won,count),'Coorte de leads do período','green'),('Ticket médio',(f'R$ {revenue/sale_count:,.2f}'.replace(',','X').replace('.',',').replace('X','.') if sale_count else 'Dados insuficientes'),'Por venda confirmada','orange')]
    if user.role_code=='after':
        tasks=scope(m.Task,user).filter(status='open')
        cards=[('Clientes vendidos',scope(m.Customer,user).count(),'Base de relacionamento','violet'),('Pós-venda pendente',tasks.filter(kind='after').count(),'Próximos contatos','blue'),('Tarefas atrasadas',tasks.filter(due_at__lt=timezone.now()).count(),'Priorize hoje','orange'),('Contatos hoje',scope(m.Activity,user).filter(occurred_at__date=timezone.localdate()).exclude(kind='note').count(),'Interações registradas','green')]
    stages=[]
    for stage in m.Stage.objects.all():
        n=leads.filter(stage=stage).count(); stages.append({'name':stage.name,'count':n,'width':max(2,rate(n,count)),'color':stage.color})
    origins=[]
    for source in m.Source.objects.all():
        n=leads.filter(source=source).count()
        if n: origins.append({'name':source.name,'count':n,'width':rate(n,count),'conversion':rate(leads.filter(source=source,sale__status='confirmed').distinct().count(),n)})
    rows=list(sales.annotate(day=TruncDate('created_at')).values('day').annotate(total=Sum('total'),count=Count('id')).order_by('day'))
    max_amount=max([float(r['total']) for r in rows]+[1]); bars=[]
    duration=(end-start).days+1
    # Avoid enormous charts for multi-year selections.
    for n in range(min(duration,62)):
        day=start+timedelta(days=n)
        entry=next((r for r in rows if r['day']==day),None)
        value=entry['total'] if entry else 0
        bars.append({'day':day,'amount':value,'height':max(2,100*float(value)/max_amount),'count':entry['count'] if entry else 0})
    task_q=scope(m.Task,user).filter(status='open').order_by('due_at')
    cost=sales.aggregate(n=Sum('cost'))['n'] or Decimal(0)
    investment=m.MarketingSpend.objects.filter(date__range=(start,end),campaign_id__in=leads.filter(campaign__isnull=False).values('campaign_id')).aggregate(n=Sum('amount'))['n']
    customer_count=m.Customer.objects.filter(pk__in=sales.values('customer_id')).annotate(first_purchase=Min('sales__created_at',filter=Q(sales__status='confirmed'))).filter(first_purchase__date__range=(start,end)).count()
    ltv_sales=scope(m.Sale,user).filter(status='confirmed'); ltv_n=ltv_sales.values('customer').distinct().count(); ltv_revenue=ltv_sales.aggregate(n=Sum('total'))['n'] or 0
    durations=[(sale.created_at-sale.lead.created_at).total_seconds()/86400 for sale in sales.select_related('lead') if sale.lead and sale.created_at>=sale.lead.created_at]
    totals=[('Leads hoje',scope(m.Lead,user).filter(created_at__date=timezone.localdate()).count()),('Leads no mês',scope(m.Lead,user).filter(created_at__date__gte=timezone.localdate().replace(day=1)).count()),('Leads sem contato',leads.filter(first_contact_at__isnull=True).count()),('Contatos',contacts),('Taxa de contato',pct(contacts,count)),('Qualificados',qualified),('Taxa de qualificação',pct(qualified,count)),('Propostas',proposals.count()),('Taxa de proposta',pct(proposals.filter(lead__isnull=False).values("lead").distinct().count(),count)),('Propostas abertas',proposals.filter(status__in=['sent','draft','viewed','negotiating']).count()),('Leads em follow-up',leads.filter(next_followup__isnull=False,stage__kind='open').count()),('Vendas',sale_count),('Leads perdidos',leads.filter(stage__kind='lost').count()),('Tempo médio até venda',f'{sum(durations)/len(durations):.1f} dias' if durations else 'Dados insuficientes')]
    if user.role_code in MANAGERS or user.role_code=='seller':
        totals += [('Margem bruta',f'R$ {revenue-cost:.2f}'),('CAC',f'R$ {investment/customer_count:.2f}' if investment is not None and customer_count else 'Dados insuficientes'),('ROI',f'{(revenue-investment)/investment*100:.1f}%' if investment else 'Dados insuficientes'),('LTV (receita histórica por cliente)',f'R$ {ltv_revenue/ltv_n:.2f}' if ltv_n else 'Dados insuficientes')]
    performance=sales.values('seller__first_name','seller__last_name').annotate(count=Count('id'),revenue=Sum('total')).order_by('-revenue')
    performance=list(performance)
    for row in performance: row['ticket']=row['revenue']/row['count'] if row['count'] else 0
    sdr=leads.values('sdr_id','sdr__first_name','sdr__last_name').annotate(count=Count('id'),contacts=Count('id',filter=Q(first_contact_at__isnull=False)),qualified=Count('id',filter=Q(qualified_at__isnull=False))).order_by('-count')
    sdr=list(sdr)
    for row in sdr:
        cohort=leads.filter(sdr_id=row['sdr_id'])
        times=[(lead.first_contact_at-lead.created_at).total_seconds()/60 for lead in cohort if lead.first_contact_at]
        row['first_contact']=f'{sum(times)/len(times):.1f} min' if times else 'Dados insuficientes'
        row['within_sla']=sum(t<=m.Company.objects.first().sla_minutes for t in times)
        row['transferred']=cohort.filter(seller__isnull=False).count()
    campaign_rows=[]
    for campaign in m.Campaign.objects.filter(pk__in=leads.values('campaign_id')):
        campaign_leads=leads.filter(campaign=campaign); campaign_sales=sales.filter(lead__campaign=campaign); earned=campaign_sales.aggregate(n=Sum('total'))['n'] or 0
        spent=campaign.marketingspend_set.filter(date__range=(start,end)).aggregate(n=Sum('amount'))['n']
        campaign_rows.append({'name':campaign.name,'leads':campaign_leads.count(),'sales':campaign_sales.count(),'revenue':earned,'spend':spent,'cpl':spent/campaign_leads.count() if spent is not None and campaign_leads.count() else None,'roi':round((earned-spent)/spent*100,1) if spent else None})
    product_rows=[]
    for product in m.Product.objects.all():
        item_q=m.SaleItem.objects.filter(sale__in=sales,variant__product=product); units=item_q.aggregate(n=Sum('quantity'))['n'] or 0
        product_rows.append({'name':product.name,'units':units,'margin':sum((item.unit_price-item.unit_cost)*item.quantity for item in item_q),'available':sum(inv.available for inv in m.Inventory.objects.filter(variant__product=product))})
    product_rows.sort(key=lambda x:x['units'],reverse=True)
    top=m.SaleItem.objects.filter(sale__in=sales).values('variant__product__name').annotate(count=Sum('quantity')).order_by('-count')[:8]
    losses=leads.filter(stage__kind='lost').values('loss_reason__name').annotate(count=Count('id')).order_by('-count')
    return {'campaign_report':campaign_rows,'product_report':product_rows,'cards':cards,'funnel':stages,'origins':origins,'bars':bars,'tasks':task_q[:6],'task_count':task_q.count(),'overdue_count':task_q.filter(due_at__lt=timezone.now()).count(),'performance':performance,'sdr_performance':sdr,'top_products':top,'losses':losses,'totals':totals,'start':start,'end':end,'lead_count':count,'sale_count':sale_count,'revenue':revenue}

def goal_value(goal):
    sales=m.Sale.objects.filter(status='confirmed',created_at__date__range=(goal.start,goal.end))
    leads=m.Lead.objects.filter(created_at__date__range=(goal.start,goal.end))
    proposals=m.Proposal.objects.filter(created_at__date__range=(goal.start,goal.end))
    activities=m.Activity.objects.filter(occurred_at__date__range=(goal.start,goal.end)).exclude(kind='note')
    if goal.user_id:
        sales=sales.filter(seller=goal.user); leads=leads.filter(Q(owner=goal.user)|Q(sdr=goal.user) if goal.user.role_code=='sdr' else Q(owner=goal.user)); proposals=proposals.filter(seller=goal.user); activities=activities.filter(user=goal.user)
    elif goal.team_id:
        sales=sales.filter(seller__team=goal.team); leads=leads.filter(owner__team=goal.team); proposals=proposals.filter(seller__team=goal.team); activities=activities.filter(user__team=goal.team)
    revenue=sales.aggregate(n=Sum('total'))['n'] or 0; count=sales.count()
    if goal.kind=='revenue': return revenue
    if goal.kind=='sales': return count
    if goal.kind=='leads': return leads.count()
    if goal.kind=='proposals': return proposals.count()
    if goal.kind=='contacts': return activities.count()
    if goal.kind=='ticket': return revenue/count if count else 0
    return 100*leads.filter(sale__status='confirmed').distinct().count()/leads.count() if leads.count() else 0
