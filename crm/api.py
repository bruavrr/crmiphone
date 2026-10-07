import hashlib, hmac, json, re
from django.conf import settings
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from . import models as m, services as s

@csrf_exempt
@require_http_methods(['POST'])
def capture_lead(request):
    key=request.headers.get('X-API-Key','')
    if not settings.LEAD_API_KEY or not hmac.compare_digest(key,settings.LEAD_API_KEY): return JsonResponse({'error':'Não autorizado'},status=401)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict): raise ValueError
        if not data.get('name') or not re.fullmatch(r'[+\d ()-]{10,25}',data.get('phone','')): return JsonResponse({'error':'Nome e telefone válidos obrigatórios'},status=400)
        stage=m.Stage.objects.filter(behavior='new',kind='open').first() or m.Stage.objects.filter(kind='open').first()
        if not stage: return JsonResponse({'error':'Configure o funil'},status=503)
        with transaction.atomic():
            source=get_source(data.get('source','Formulário'))
            customer=m.Customer.objects.filter(contact_key=m.normalized_phone(data['phone']),anonymized_at__isnull=True).first()
            if not customer:
                customer=m.Customer(first_name=data['name'][:100],phone=data['phone'],email=data.get('email',''),consent=data.get('consent') is True)
                if customer.consent: customer.consent_at=__import__('django.utils.timezone',fromlist=['now']).now()
                customer.full_clean(); customer.save()
            lead=m.Lead(customer=customer,source=source,stage=stage,notes=data.get('notes','')[:5000])
            for key in ['utm_source','utm_medium','utm_campaign','utm_content','utm_term']: setattr(lead,key,str(data.get(key,''))[:150])
            s.create_lead(lead)
        return JsonResponse({'id':str(lead.pk),'status':'created'},status=201)
    except (ValueError,TypeError,ValidationError): return JsonResponse({'error':'Dados inválidos'},status=400)

def get_source(name): return m.Source.objects.get_or_create(name=str(name)[:100])[0]

@csrf_exempt
@require_http_methods(['GET','POST'])
def meta_webhook(request):
    if request.method=='GET':
        token=request.GET.get('hub.verify_token','')
        if settings.META_VERIFY_TOKEN and hmac.compare_digest(token,settings.META_VERIFY_TOKEN) and request.GET.get('hub.mode')=='subscribe': return HttpResponse(request.GET.get('hub.challenge',''))
        return HttpResponse(status=403)
    signature=request.headers.get('X-Hub-Signature-256','')
    expected='sha256='+hmac.new(settings.META_APP_SECRET.encode(),request.body,hashlib.sha256).hexdigest()
    if not settings.META_APP_SECRET or not hmac.compare_digest(signature,expected): return HttpResponse(status=403)
    try:
        payload=json.loads(request.body)
        events=[]
        for entry in payload.get('entry',[]):
            for change in entry.get('changes',[]):
                val=change.get('value',{}); account=val.get('metadata',{}).get('phone_number_id','')
                integration=m.Integration.objects.filter(channel='whatsapp',enabled=True,phone_id=account).first()
                if not integration: continue
                names={x.get('wa_id'):x.get('profile',{}).get('name') for x in val.get('contacts',[])}
                for message in val.get('messages',[]):
                    if message.get('type')=='text': events.append(('whatsapp',message.get('from'),message.get('id'),message.get('text',{}).get('body',''),names.get(message.get('from'))))
                for status in val.get('statuses',[]):
                    if status.get('status') in {'sent','delivered','read','failed'}: m.Message.objects.filter(external_id=status.get('id')).update(result=status['status'])
            if m.Integration.objects.filter(channel='instagram',enabled=True,account_id=entry.get('id')).exists():
                for event in entry.get('messaging',[]):
                    msg=event.get('message',{})
                    if msg.get('text') and not msg.get('is_echo'): events.append(('instagram',event.get('sender',{}).get('id'),msg.get('mid'),msg['text'],None))
        for channel,sender,external_id,body,name in events:
            if not sender or not external_id: continue
            try:
                with transaction.atomic():
                    if m.Message.objects.filter(external_id=external_id).exists(): continue
                    conv=m.Conversation.objects.filter(channel=channel,external_id=sender).first()
                    if not conv:
                        customer=m.Customer.objects.filter(contact_key=m.normalized_phone(sender),anonymized_at__isnull=True).first() if channel=='whatsapp' else None
                        if not customer: customer=m.Customer.objects.create(first_name=(name or f'Contato {channel} {sender}')[:100],phone=sender if channel=='whatsapp' else '',whatsapp=sender if channel=='whatsapp' else '')
                        stage=m.Stage.objects.filter(behavior='new',kind='open').first() or m.Stage.objects.filter(kind='open').first()
                        if not stage: return HttpResponse(status=503)
                        lead=m.Lead.objects.filter(customer=customer,stage__kind='open').order_by('-created_at').first() or s.create_lead(m.Lead(customer=customer,source=get_source('WhatsApp' if channel=='whatsapp' else 'Instagram Direct'),stage=stage))
                        conv=m.Conversation.objects.create(customer=customer,lead=lead,owner=lead.owner,channel=channel,external_id=sender)
                    m.Message.objects.create(conversation=conv,direction='in',body=body[:10000],external_id=external_id,result='received')
                    conv.status='unanswered'; conv.save()
                    s.notify(conv.owner,'Nova mensagem recebida',f'/inbox/{conv.pk}/')
                    if conv.lead: s.history(conv.lead,None,'Mensagem recebida pela API oficial de '+channel+'.')
            except IntegrityError: continue  # provider retried the same event concurrently
        return HttpResponse(status=200)
    except (ValueError,TypeError,AttributeError): return HttpResponse(status=400)
