from django.db.models import Q
from django.core.exceptions import PermissionDenied
from . import models as m
MANAGERS={'admin','manager'}
ACCESS={
'dashboard':{'admin','manager','sdr','seller','after'},'leads':{'admin','manager','sdr','seller'},'customers':{'admin','manager','sdr','seller','after'},'pipeline':{'admin','manager','sdr','seller'},'inbox':{'admin','manager','sdr','seller','after'},'tasks':{'admin','manager','sdr','seller','after'},'activities':{'admin','manager','sdr','seller','after'},'products':{'admin','manager','seller'},'variants':{'admin','manager','seller'},'inventory':{'admin','manager','seller'},'movements':{'admin','manager'},'trades':{'admin','manager','seller'},'proposals':{'admin','manager','seller'},'sales':{'admin','manager','seller'},'payments':{'admin','manager','seller'},'commissions':{'admin','manager','seller'},'goals':{'admin','manager','seller','sdr'},'reports':{'admin','manager'},'aftercare':{'admin','manager','after','seller'},'reactivation':{'admin','manager','after','seller'},'reactivation-campaigns':{'admin','manager','after'},'notifications':{'admin','manager','sdr','seller','after'},'users':{'admin'},'teams':{'admin'},'sources':{'admin'},'campaigns':{'admin','manager'},'investments':{'admin','manager'},'stages':{'admin'},'loss-reasons':{'admin'},'automations':{'admin'},'integrations':{'admin'},'company':{'admin'},'scoring':{'admin'},'commission-rules':{'admin'},'audit':{'admin','manager'},'settings':{'admin','manager'}}
def allowed(user,module): return user.is_authenticated and user.role_code in ACCESS.get(module,set())
def require(user,module,write=False):
    if not allowed(user,module): raise PermissionDenied('Você não tem acesso a este módulo.')
    if write and user.role_code not in MANAGERS and module in {'products','variants','inventory','goals','commissions'}: raise PermissionDenied('Alteração restrita à gestão.')
def scope(model,user):
    qs=model.objects.all()
    if user.role_code in MANAGERS: return qs
    lead_ids=m.Lead.objects.filter(Q(owner=user)|Q(sdr=user)|Q(seller=user)|Q(proposal__seller=user)|Q(sale__seller=user)).values('id')
    customers=m.Customer.objects.filter(Q(leads__id__in=lead_ids)|Q(created_by=user)|Q(proposal__seller=user)|Q(sales__seller=user))
    if user.role_code=='after': customers=m.Customer.objects.filter(sales__status='confirmed')
    ids=customers.values('id')
    if model==m.User: return qs.filter(pk=user.pk)
    if model==m.Lead: return qs.filter(pk__in=lead_ids)
    if model==m.Customer: return qs.filter(pk__in=ids).distinct()
    if model==m.Task: return qs.filter(owner=user)
    if model in {m.Proposal,m.Sale}: return qs.filter(seller=user)
    if model==m.Payment: return qs.filter(sale__seller=user)
    if model==m.Commission: return qs.filter(user=user)
    if model==m.Goal: return qs.filter(Q(user=user)|Q(user__isnull=True,team=user.team) if user.team else Q(user=user))
    if model==m.Conversation: return qs.filter(Q(owner=user)|Q(customer__in=ids))
    if model in {m.Activity,m.UsedDevice}: return qs.filter(customer__in=ids)
    if model==m.Notification: return qs.filter(user=user)
    if model==m.ReactivationCampaign: return qs.filter(owner=user)
    return qs
