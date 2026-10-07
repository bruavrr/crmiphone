import csv, hashlib, json, re, secrets
from datetime import timedelta, datetime, time
from decimal import Decimal
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, Max
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse, Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import models as m, services as s
from .permissions import require, allowed, scope, MANAGERS
from .registry import REGISTRY, LABELS
from .forms import build_form, FIELDS, ItemFormSet
from .metrics import metrics, period, goal_value

class SecureLoginView(LoginView):
    template_name='crm/login.html'
    def dispatch(self,request,*args,**kwargs):
        self.key=hashlib.sha256((request.META.get('REMOTE_ADDR','')+':'+request.POST.get('username','').lower()).encode()).hexdigest()
        if request.method=='POST':
            row=m.LoginAttempt.objects.filter(pk=self.key).first()
            if row and row.failures>=8 and timezone.now()-row.window_start<timedelta(minutes=15):
                return render(request,self.template_name,{'form':self.get_form(),'blocked':True},status=429)
        return super().dispatch(request,*args,**kwargs)
    def form_invalid(self,form):
        with transaction.atomic():
            row,_=m.LoginAttempt.objects.select_for_update().get_or_create(key=self.key)
            if timezone.now()-row.window_start>timedelta(minutes=15): row.window_start=timezone.now(); row.failures=0
            row.failures+=1; row.save()
        return super().form_invalid(form)
    def form_valid(self,form):
        m.LoginAttempt.objects.filter(pk=self.key).delete()
        return super().form_valid(form)

def module_info(module):
    if module not in REGISTRY: raise Http404
    return REGISTRY[module]
def snapshot(obj):
    result={}
    for field in obj._meta.fields:
        if field.name in {'password','last_login','is_demo','created_at','updated_at'}: continue
        value=getattr(obj,field.attname)
        result[str(field.verbose_name)]=str(value) if value is not None else ''
    return result

def format_value(obj,key):
    display=getattr(obj,'get_'+key+'_display',None)
    value=display() if display else getattr(obj,key,'')
    if value is None or value=='': return '—'
    if isinstance(value,bool): return 'Sim' if value else 'Não'
    if isinstance(value,Decimal) and key in {'percent','commission_percent'}: return f'{value}%'.replace('.',',')
    if isinstance(value,Decimal) and key=='target' and getattr(obj,'kind','') not in {'revenue','ticket'}: return str(value)
    if isinstance(value,Decimal): return f'R$ {value:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    if isinstance(value,datetime): return timezone.localtime(value).strftime('%d/%m/%Y %H:%M')
    if isinstance(value,time): return value.strftime('%H:%M')
    if hasattr(value,'strftime'): return value.strftime('%d/%m/%Y')
    return str(value)

@login_required
def dashboard(request):
    data=metrics(request.user,request.GET); data.update(title='Visão geral',subtitle='Sua operação comercial, em um só lugar.',module='dashboard')
    return render(request,'crm/dashboard.html',data)

SEARCH_FIELDS={m.Lead:['customer__first_name','customer__last_name','customer__phone','customer__whatsapp','customer__email','customer__instagram','product__name','desired_model','utm_campaign'],m.Customer:['first_name','last_name','phone','whatsapp','email','instagram'],m.Product:['name','model','brand'],m.Variant:['product__name','imei','serial','capacity','color'],m.Inventory:['variant__product__name','variant__imei','variant__serial'],m.InventoryMovement:['variant__product__name','reason'],m.UsedDevice:['model','imei','customer__first_name'],m.Proposal:['customer__first_name','customer__phone'],m.Sale:['customer__first_name','customer__phone'],m.Task:['title','customer__first_name'],m.Conversation:['customer__first_name','customer__phone'],m.User:['username','first_name','last_name']}
def filtered(qs,model,params):
    q=params.get('q','').strip()
    if q:
        condition=Q()
        for field in SEARCH_FIELDS.get(model,[]): condition|=Q(**{field+'__icontains':q})
        if q.upper().startswith(('VEN-','PROP-')): q=q.split('-',1)[1]
        if len(q)>=4 and re.fullmatch('[0-9a-fA-F-]+',q) and model not in {m.User}: condition|=Q(id__icontains=q.replace('-',''))
        if not condition:
            for field in model._meta.fields:
                if field.get_internal_type() in {'CharField','TextField'}: condition|=Q(**{field.name+'__icontains':q})
        qs=qs.filter(condition) if condition else qs.none()
    names={f.name for f in model._meta.fields}
    for name in ['owner','source','stage','product','seller','sdr','campaign','status','channel','city','variant']:
        if params.get(name) and name in names:
            field=model._meta.get_field(name)
            if field.is_relation:
                try: field.target_field.to_python(params[name])
                except (ValidationError,ValueError): return qs.none()
            qs=qs.filter(**{name:params[name]})
    if model==m.Lead:
        temp=params.get('temperature')
        if temp=='cold': qs=qs.filter(score__lte=30)
        elif temp=='warm': qs=qs.filter(score__gt=30,score__lte=60)
        elif temp=='hot': qs=qs.filter(score__gt=60)
        if params.get('stale'): qs=qs.filter(stage__kind='open').filter(Q(last_interaction__lt=timezone.now()-timedelta(days=3))|Q(last_interaction__isnull=True,created_at__lt=timezone.now()-timedelta(days=3)))
    if model==m.Task and params.get('overdue'): qs=qs.filter(status='open',due_at__lt=timezone.now())
    if params.get('start'):
        from datetime import date
        try: qs=qs.filter(created_at__date__gte=date.fromisoformat(params['start']))
        except ValueError: pass
    if params.get('end'):
        from datetime import date
        try: qs=qs.filter(created_at__date__lte=date.fromisoformat(params['end']))
        except ValueError: pass
    money='budget' if model==m.Lead else 'total' if model==m.Sale else 'price' if model==m.Variant else None
    for param,lookup in [('min','gte'),('max','lte')]:
        if money and params.get(param):
            try: qs=qs.filter(**{money+'__'+lookup:Decimal(params[param])})
            except Exception: pass
    return qs.distinct()

def filter_options(request,model):
    names={f.name for f in model._meta.fields}; options=[]
    for name,label,rel in [('owner','Responsável',m.User),('seller','Vendedor',m.User),('sdr','SDR',m.User),('source','Origem',m.Source),('campaign','Campanha',m.Campaign),('stage','Etapa',m.Stage),('product','Produto',m.Product)]:
        if name in names:
            values=scope(rel,request.user)
            if rel==m.User and request.user.role_code in MANAGERS: values=m.User.objects.filter(is_active=True)
            options.append({'name':name,'label':label,'values':[(str(x.pk),str(x)) for x in values],'selected':request.GET.get(name,'')})
    for name in ['status','channel']:
        if name in names and model._meta.get_field(name).choices:
            options.append({'name':name,'label':LABELS[name],'values':model._meta.get_field(name).choices,'selected':request.GET.get(name,'')})
    if model==m.Lead: options.append({'name':'temperature','label':'Temperatura','values':[('cold','Frio'),('warm','Morno'),('hot','Quente')],'selected':request.GET.get('temperature','')})
    return options

@login_required
def listing(request,module):
    require(request.user,module); model,singular,title,columns=module_info(module)
    qs=filtered(scope(model,request.user),model,request.GET)
    qs=qs.order_by('-date_joined' if model==m.User else '-created_at')
    if model==m.Lead: qs=qs.select_related('customer','source','owner','stage')
    if model==m.Task: qs=qs.select_related('customer','owner')
    if request.GET.get('export')=='csv':
        response=HttpResponse(content_type='text/csv; charset=utf-8'); response['Content-Disposition']=f'attachment; filename="{module}.csv"'
        response.write('\ufeff'); writer=csv.writer(response); writer.writerow([LABELS.get(k,k) for k in columns])
        for obj in qs.iterator(): writer.writerow([safe_csv(format_value(obj,k)) for k in columns])
        s.audit(request.user,model(),'Exportação CSV',after={'módulo':module,'registros':qs.count()})
        return response
    page=Paginator(qs,20).get_page(request.GET.get('page'))
    rows=[]
    for obj in page:
        rows.append({'obj':obj,'cells':[{'value':format_value(obj,k),'key':k} for k in columns],'url':f'/{module}/{obj.pk}/'})
    goals=[]
    if module=='goals':
        for obj in page:
            value=goal_value(obj); goals.append({'obj':obj,'value':round(value,2),'progress':min(100,round(float(value)/float(obj.target)*100,1)) if obj.target else 0})
    editable=module in FIELDS or module=='users'
    can_write=editable and (request.user.role_code in MANAGERS or module not in {'products','variants','inventory','goals','commissions'})
    data={'title':title,'subtitle':f'{qs.count()} registros · informações atualizadas da sua operação','module':module,'singular':singular,'headers':[LABELS.get(k,k) for k in columns],'rows':rows,'page':page,'filters':filter_options(request,model),'can_create':can_write,'favorites':m.SavedFilter.objects.filter(user=request.user,module=module),'goals':goals,'querystring':urlencode({k:v for k,v in request.GET.items() if k!='page'})}
    if module=='inbox': data['integration_configured']=m.Integration.objects.filter(enabled=True,channel__in=['whatsapp','instagram']).exists() and bool(__import__('django.conf',fromlist=['settings']).settings.META_ACCESS_TOKEN)
    return render(request,'crm/list.html',data)

def safe_csv(value): return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value

@login_required
def edit(request,module,pk=None):
    require(request.user,module,write=True); model,singular,title,columns=module_info(module)
    if module not in FIELDS and module!='users': raise PermissionDenied('Registro gerenciado por regras comerciais.')
    obj=get_object_or_404(scope(model,request.user),pk=pk) if pk else None
    initial={}
    for name in ['customer','lead']:
        if request.GET.get(name): initial[name]=request.GET[name]
    if module in {'tasks','inbox'}: initial['owner']=request.user.pk
    if module=='leads': initial['stage']=m.Stage.objects.filter(behavior='new',kind='open').first() or m.Stage.objects.filter(kind='open').first(); initial['owner']=request.user.pk if request.user.role_code not in MANAGERS else None
    if module=='proposals': initial['seller']=request.user.pk
    old_files={name:(getattr(obj,name).storage,getattr(obj,name).name) for name in ['photo','logo'] if obj and hasattr(obj,name) and getattr(obj,name)}
    old=snapshot(obj) if obj else {}; old_stage=obj.stage if obj and module=='leads' else None; old_owner=obj.owner if obj and module=='leads' else None
    try: form=build_form(module,model,request.user,request.POST or None,request.FILES or None,obj,initial)
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages)); return redirect(f'/{module}/{pk}/')
    formset=ItemFormSet(request.POST or None,instance=obj,prefix='items') if module=='proposals' else None
    if request.method=='POST' and form.is_valid() and (formset is None or formset.is_valid()):
        try:
            with transaction.atomic():
                instance=form.save(commit=False)
                if module=='customers':
                    if not obj: instance.created_by=request.user
                    if instance.consent and not instance.consent_at: instance.consent_at=timezone.now()
                    elif not instance.consent: instance.consent_at=None
                if module=='activities': s.record_activity(instance,request.user)
                elif module=='leads':
                    if not obj:
                        if request.user.role_code not in MANAGERS: instance.owner=request.user; instance.sdr=request.user if request.user.role_code=='sdr' else None; instance.seller=request.user if request.user.role_code=='seller' else None
                        s.create_lead(instance,request.user)
                    else:
                        target_stage=instance.stage; reason=instance.loss_reason
                        instance.stage=old_stage; instance.save()
                        if target_stage!=old_stage: s.change_stage(instance,target_stage,request.user,reason)
                        if instance.owner!=old_owner:
                            s.history(instance,request.user,f'Responsável alterado: {old_owner or "Sem responsável"} → {instance.owner or "Sem responsável"}.')
                            s.notify(instance.owner,'Lead atribuído para você',f'/leads/{instance.pk}/')
                elif module=='movements': instance=s.move_stock(instance.variant,instance.kind,instance.quantity,request.user,instance.reason)
                else: instance.save()
                form.save_m2m()
                if module=='variants': m.Inventory.objects.get_or_create(variant=instance)
                if formset:
                    formset.instance=instance; formset.save()
                    s.validate_quote(instance,list(instance.items.all()))
                if module=='reactivation-campaigns' and not obj:
                    cutoff=timezone.now()-timedelta(days=instance.months*30)
                    clients=scope(m.Customer,request.user).annotate(last_purchase=Max('sales__created_at',filter=Q(sales__status='confirmed'))).filter(last_purchase__lte=cutoff,consent=True,anonymized_at__isnull=True)
                    for customer in clients: s.create_task(None,f'{instance.name} · {customer}',timezone.now(),'reactivate',f'campaign:{instance.pk}:{customer.pk}',owner=instance.owner,customer=customer)
                if module=='users' and obj and obj.pk==request.user.pk and (not instance.is_active or instance.role_code!='admin'): raise ValidationError('Você não pode remover seu próprio acesso administrativo.')
                if module=='stages' and obj and old.get('Tipo')!=instance.kind and instance.lead_set.exists(): raise ValidationError('Tipo de etapa com leads vinculados não pode ser alterado.')
                s.audit(request.user,instance,'Alteração' if obj else 'Criação',old,snapshot(instance))
                for name,(storage,old_name) in old_files.items():
                    if getattr(instance,name).name!=old_name: transaction.on_commit(lambda storage=storage,old_name=old_name: storage.delete(old_name))
            messages.success(request,f'{singular} salvo com sucesso.'); return redirect(f'/{module}/{instance.pk}/')
        except (ValidationError,IntegrityError) as exc: form.add_error(None,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Registro duplicado ou relacionamento inválido.')
    return render(request,'crm/form.html',{'form':form,'formset':formset,'module':module,'title':f'{"Editar" if obj else "Novo"} {singular.lower()}','subtitle':'Preencha os dados. Todas as informações são salvas no banco.','obj':obj})

@login_required
def detail(request,module,pk):
    require(request.user,module); model,singular,title,columns=module_info(module)
    obj=get_object_or_404(scope(model,request.user),pk=pk)
    data={'obj':obj,'module':module,'title':str(obj) if module not in {'audit','notifications'} else singular,'subtitle':f'{singular} · registro {str(pk)[:8].upper()}','fields':[{'label':LABELS.get(f.name,str(f.verbose_name)),'value':format_value(obj,f.name)} for f in model._meta.fields if f.name not in {'password','id','is_demo','is_superuser','is_staff','contact_key','round_robin_cursor','groups','user_permissions'}],'editable':module in FIELDS or module=='users'}
    if request.user.role_code not in MANAGERS and module in {'products','variants','inventory','goals','commissions'}: data['editable']=False
    customer=obj if module=='customers' else obj.customer if hasattr(obj,'customer') else None
    lead=obj if module=='leads' else obj.lead if hasattr(obj,'lead') else None
    if customer:
        data.update(customer=customer,related_leads=scope(m.Lead,request.user).filter(customer=customer),activities=scope(m.Activity,request.user).filter(customer=customer).order_by('-occurred_at')[:40],customer_tasks=scope(m.Task,request.user).filter(customer=customer).order_by('due_at')[:10])
        if allowed(request.user,'proposals'): data['customer_proposals']=scope(m.Proposal,request.user).filter(customer=customer)
        if allowed(request.user,'sales'): data['customer_sales']=scope(m.Sale,request.user).filter(customer=customer)
    if module=='customers':
        visible_leads=m.Lead.objects.filter(customer=customer) if request.user.role_code=='after' else scope(m.Lead,request.user).filter(customer=customer)
        data['history']=m.History.objects.filter(lead__in=visible_leads).select_related('user').order_by('-created_at')[:60]
    if lead: data.update(lead=lead,history=lead.history.select_related('user').order_by('-created_at')[:60],stages=m.Stage.objects.all(),loss_reasons=m.LossReason.objects.all(),transfer_users=m.User.objects.filter(is_active=True,available=True,role='seller'))
    if module in {'products','trades'}: data['photos']=obj.photos.all()
    if module=='products': data['variants']=obj.variants.select_related('inventory')
    if module=='inventory': data['stock_movements']=m.InventoryMovement.objects.filter(variant=obj.variant).select_related('user').order_by('-created_at')[:50]
    if module=='proposals': data['items']=obj.items.select_related('variant__product')
    if module=='sales': data.update(items=obj.items.select_related('variant__product'),payments=obj.payments.all())
    if module=='inbox': data['chat_messages']=obj.messages.order_by('created_at'); data['integration_configured']=__import__('django.conf',fromlist=['settings']).settings.META_ACCESS_TOKEN and m.Integration.objects.filter(channel=obj.channel,enabled=True).exists()
    if module=='audit': data.update(audit_before=obj.before,audit_after=obj.after)
    return render(request,'crm/detail.html',data)

@login_required
@require_POST
def delete(request,module,pk):
    require(request.user,module,write=True)
    if request.user.role_code not in MANAGERS: raise PermissionDenied('Exclusão restrita à gestão.')
    if module in {'sales','payments','commissions','movements','audit','company','users'}: raise PermissionDenied('Use cancelamento ou desativação para preservar o histórico.')
    model,*_=module_info(module); obj=get_object_or_404(scope(model,request.user),pk=pk)
    try:
        with transaction.atomic(): s.audit(request.user,obj,'Exclusão',snapshot(obj)); obj.delete()
        messages.success(request,'Registro excluído.'); return redirect(f'/{module}/')
    except ProtectedError:
        messages.error(request,'Há registros vinculados. Preserve o histórico ou anonimize o cliente.'); return redirect(f'/{module}/{pk}/')

@login_required
@require_POST
def action(request,module,pk,action):
    require(request.user,module); model,*_=module_info(module); obj=get_object_or_404(scope(model,request.user),pk=pk)
    try:
        with transaction.atomic():
            obj=scope(model,request.user).select_for_update().get(pk=pk)
            if module in {'products','trades'} and action=='photo':
                require(request.user,module,write=True)
                from django import forms
                image=forms.ImageField().clean(request.FILES.get('image'))
                if image.size>5*1024*1024: raise ValidationError('Limite de imagem: 5 MB.')
                attachment=m.Attachment.objects.create(image=image,uploaded_by=request.user,**{'product' if module=='products' else 'device':obj})
                s.audit(request.user,attachment,'Foto anexada')
            elif module in {'products','trades'} and action=='photo-remove':
                require(request.user,module,write=True)
                if request.POST.get('photo'):
                    photo=get_object_or_404(obj.photos,pk=request.POST['photo']); photo.image.delete(save=False); s.audit(request.user,photo,'Foto removida'); photo.delete()
                elif obj.photo: obj.photo.delete(save=True); s.audit(request.user,obj,'Foto principal removida')
            elif module=='leads' and action=='stage':
                stage=get_object_or_404(m.Stage,pk=request.POST.get('stage')); reason=m.LossReason.objects.filter(pk=request.POST.get('reason')).first() if request.POST.get('reason') else None
                s.change_stage(obj,stage,request.user,reason)
            elif module=='leads' and action in {'assign','redistribute'}:
                if request.user.role_code not in MANAGERS: raise PermissionDenied
                s.assign(obj,request.user,force=action=='redistribute')
            elif module=='leads' and action=='transfer':
                if request.user.role_code not in MANAGERS|{'sdr'}: raise PermissionDenied
                seller=get_object_or_404(m.User,pk=request.POST.get('seller'),role='seller',is_active=True,available=True)
                if not obj.qualified_at: raise ValidationError('Qualifique o lead antes de transferir.')
                old=str(obj.owner); obj.owner=obj.seller=seller; obj.save()
                s.history(obj,request.user,f'Lead transferido de {old} para {seller}.'); s.audit(request.user,obj,'Transferência',{'responsável':old},{'responsável':str(seller)})
                s.notify(seller,'Lead qualificado recebido',f'/leads/{obj.pk}/')
            elif module=='tasks' and action=='complete':
                obj.status='done'; obj.save(); s.audit(request.user,obj,'Tarefa concluída')
                if obj.lead:
                    obj.lead.next_followup=m.Task.objects.filter(lead=obj.lead,status='open').order_by('due_at').values_list('due_at',flat=True).first(); obj.lead.save(update_fields=['next_followup','updated_at'])
                if obj.lead: s.history(obj.lead,request.user,'Tarefa concluída: '+obj.title)
            elif module=='customers' and action=='anonymize':
                if request.user.role_code not in MANAGERS: raise PermissionDenied
                s.anonymize(obj,request.user)
            elif module in {'customers','leads'} and action=='whatsapp':
                customer=obj if module=='customers' else obj.customer
                phone=re.sub(r'\D','',customer.whatsapp or customer.phone)
                if len(phone) in {10,11}: phone='55'+phone
                if not 10<=len(phone)<=15: raise ValidationError('Cadastre um telefone válido.')
                s.audit(request.user,customer,'WhatsApp aberto (envio não confirmado)')
                if module=='leads': s.history(obj,request.user,'Conversa aberta no WhatsApp; envio de mensagem não confirmado.')
                return redirect('https://wa.me/'+phone)
            elif module=='proposals' and action=='status':
                new_status=request.POST.get('status')
                if obj.status in {'accepted','expired','refused'} or new_status not in {'draft','sent','viewed','negotiating','refused'}: raise ValidationError('Transição de status inválida.')
                if new_status=='sent': s.send_proposal(obj,request.user)
                else:
                    old_status=obj.status; obj.status=new_status; obj.save(); s.audit(request.user,obj,'Status de proposta',{'status':old_status},{'status':new_status})
                    if obj.lead: s.history(obj.lead,request.user,'Status da proposta registrado manualmente: '+obj.get_status_display())
            elif module=='proposals' and action=='send': s.send_proposal(obj,request.user)
            elif module=='proposals' and action=='sell':
                sale=s.confirm_sale(obj,request.user); messages.success(request,'Venda registrada, estoque e comissão atualizados.'); return redirect(f'/sales/{sale.pk}/')
            elif module=='sales' and action=='cancel':
                if request.user.role_code not in MANAGERS: raise PermissionDenied
                s.cancel_sale(obj,request.user)
            elif module=='sales' and action=='payment':
                payment=get_object_or_404(m.Payment,sale=obj,pk=request.POST.get('payment'))
                if obj.status!='confirmed' or payment.status=='cancelled': raise ValidationError('Venda ou pagamento cancelado.')
                payment.status='confirmed'; payment.confirmed_at=timezone.now(); payment.save(); s.audit(request.user,payment,'Pagamento confirmado')
                if obj.lead: s.history(obj.lead,request.user,f'Pagamento confirmado: R$ {payment.amount}.')
            elif module=='notifications' and action=='read': obj.read=True; obj.save()
            elif module=='inbox' and action=='send':
                from .integrations import send_message
                send_message(obj,request.POST.get('body',''),request.user)
            else: raise Http404
        messages.success(request,'Operação concluída.')
        if request.headers.get('Accept')=='application/json': return JsonResponse({'ok':True})
    except (ValidationError,IntegrityError) as exc:
        error=' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Operação conflitante. Atualize e tente novamente.'
        if request.headers.get('Accept')=='application/json': return JsonResponse({'ok':False,'error':error},status=400)
        messages.error(request,error)
    return redirect(f'/{module}/{pk}/')

@login_required
def pipeline(request):
    require(request.user,'pipeline'); leads=filtered(scope(m.Lead,request.user),m.Lead,request.GET).select_related('customer','owner','product')
    columns=[{'stage':stage,'leads':leads.filter(stage=stage)} for stage in m.Stage.objects.all()]
    return render(request,'crm/pipeline.html',{'title':'Pipeline comercial','subtitle':'Acompanhe cada oportunidade, do primeiro contato ao pós-venda.','module':'pipeline','columns':columns,'filters':filter_options(request,m.Lead),'loss_reasons':m.LossReason.objects.all()})

@login_required
def search(request):
    q=request.GET.get('q','').strip(); groups=[]
    if q:
        for module in ['customers','leads','products','variants','trades','proposals','sales','tasks']:
            if allowed(request.user,module):
                model,_,title,_=REGISTRY[module]
                results=filtered(scope(model,request.user),model,{'q':q})[:8]
                groups.append({'title':title,'module':module,'rows':[{'title':str(obj),'url':f'/{module}/{obj.pk}/'} for obj in results]})
    return render(request,'crm/search.html',{'title':'Busca global','subtitle':'Clientes, produtos, IMEI, propostas e vendas.','groups':groups,'q':q})

@login_required
def reports(request):
    require(request.user,'reports'); data=metrics(request.user,request.GET)
    if request.GET.get('export')=='csv':
        response=HttpResponse(content_type='text/csv; charset=utf-8'); response['Content-Disposition']='attachment; filename="relatorio.csv"'; response.write('\ufeff')
        writer=csv.writer(response); writer.writerow(['Indicador','Valor']); writer.writerows([(safe_csv(k),safe_csv(str(v))) for k,v in data['totals']]); return response
    data.update(title='Relatórios & inteligência',subtitle='Indicadores calculados a partir dos registros da operação.',module='reports')
    return render(request,'crm/reports.html',data)

@login_required
def settings_view(request):
    require(request.user,'settings')
    cards=[{'name':REGISTRY[module][2],'url':f'/{module}/','description':desc} for module,desc in [('company','Identidade, expediente e intervalos dos fluxos'),('users','Perfis, acessos, disponibilidade e comissões'),('teams','Organização da equipe comercial'),('stages','Etapas do funil comercial'),('sources','Canais de aquisição'),('campaigns','Orçamento e atribuição de campanhas'),('investments','Despesas por data para CAC e ROI'),('loss-reasons','Padronize as perdas para analisar causas'),('automations','Gatilho → condição → ação'),('scoring','Critérios de temperatura dos leads'),('commission-rules','Percentuais por produto ou categoria'),('integrations','Meta e arquitetura de IA'),('audit','Histórico de alterações e responsáveis')] if allowed(request.user,module)]
    return render(request,'crm/settings.html',{'title':'Configurações','subtitle':'Personalize sua operação com controle e segurança.','module':'settings','settings_cards':cards})

@login_required
def aftercare(request,module):
    require(request.user,module)
    qs=scope(m.Customer,request.user).filter(anonymized_at__isnull=True).annotate(last_purchase=Max('sales__created_at',filter=Q(sales__status='confirmed')))
    months=int(request.GET.get('months','6')) if request.GET.get('months','6').isdigit() else 6
    if module=='reactivation':
        cutoff=timezone.now()-timedelta(days=months*30)
        qs=qs.filter(Q(last_purchase__lte=cutoff)|Q(last_purchase__isnull=True,leads__stage__kind='lost')).distinct()
        if request.GET.get('consent'): qs=qs.filter(consent=True)
        if request.GET.get('restocked'): qs=qs.filter(leads__product__variants__inventory__quantity__gt=0,leads__stage__kind='lost').distinct()
    else: qs=qs.filter(last_purchase__isnull=False)
    if request.GET.get('q'): qs=filtered(qs,m.Customer,request.GET)
    page=Paginator(qs.order_by('last_purchase'),20).get_page(request.GET.get('page'))
    return render(request,'crm/aftercare.html',{'title':'Clientes para reativar' if module=='reactivation' else 'Pós-venda & relacionamento','subtitle':'Relacionamento contínuo e oportunidades de upgrade.','module':module,'customers_page':page,'months':months,'upgrade_cutoff':timezone.now()-timedelta(days=365)})

@login_required
def print_proposal(request,pk):
    require(request.user,'proposals'); proposal=get_object_or_404(scope(m.Proposal,request.user),pk=pk)
    return render(request,'crm/proposal_print.html',{'proposal':proposal,'items':proposal.items.select_related('variant__product'),'company':s.company()})

@login_required
@require_POST
def save_filter(request,module):
    require(request.user,module)
    name=request.POST.get('name','').strip()[:100]
    if name:
        params={k:v for k,v in request.POST.items() if k not in {'csrfmiddlewaretoken','name'}}
        m.SavedFilter.objects.update_or_create(user=request.user,module=module,name=name,defaults={'params':params})
        messages.success(request,'Filtro favorito salvo.')
    return redirect(f'/{module}/?'+urlencode(params if name else {}))

def privacy(request): return render(request,'crm/privacy.html')

@login_required
def image(request,module,pk,attachment=None):
    if module!='company': require(request.user,module)
    model,*_=module_info(module); obj=get_object_or_404(scope(model,request.user),pk=pk)
    if module not in {'products','trades','company'}: raise Http404
    if attachment: file=get_object_or_404(obj.photos,pk=attachment).image
    else: file=getattr(obj,'photo',None) or getattr(obj,'logo',None)
    if not file: raise Http404
    response=FileResponse(file.open('rb')); response['Cache-Control']='private, no-store'; return response

def health(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1'); cursor.fetchone()
        return JsonResponse({'status':'ok'})
    except Exception: return JsonResponse({'status':'unavailable'},status=503)
