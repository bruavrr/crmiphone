"""Official Meta transport. Never fabricate inbound messages or successful delivery."""
import json, urllib.request, urllib.error
from django.conf import settings
from django.core.exceptions import ValidationError
from . import models as m
from .services import audit, record_activity

def send_message(conversation,body,user):
    body=body.strip()
    if not body or len(body)>4096: raise ValidationError('Mensagem deve conter entre 1 e 4096 caracteres.')
    integration=m.Integration.objects.filter(channel=conversation.channel,enabled=True).first()
    if not integration or not settings.META_ACCESS_TOKEN: raise ValidationError('Integração oficial não configurada. Configure os IDs e a variável META_ACCESS_TOKEN no servidor.')
    if conversation.channel=='whatsapp':
        if not integration.phone_id: raise ValidationError('Phone Number ID obrigatório.')
        import re
        phone=re.sub(r'\D','',conversation.customer.whatsapp or conversation.customer.phone)
        if len(phone) in {10,11}: phone='55'+phone
        payload={'messaging_product':'whatsapp','to':phone,'type':'text','text':{'body':body}}
        endpoint=f'https://graph.facebook.com/v23.0/{integration.phone_id}/messages'
    else:
        if not integration.account_id or not conversation.external_id: raise ValidationError('Account ID e destinatário externo obrigatórios.')
        payload={'recipient':{'id':conversation.external_id},'message':{'text':body}}
        endpoint=f'https://graph.instagram.com/v23.0/{integration.account_id}/messages'
    req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+settings.META_ACCESS_TOKEN,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=15) as response: result=json.load(response)
    except (urllib.error.URLError,ValueError): raise ValidationError('A API oficial não confirmou o envio. Verifique configuração, permissões e janela de atendimento da Meta.')
    external_id=(result.get('messages') or [{}])[0].get('id') or result.get('message_id')
    if not external_id: raise ValidationError('A API não retornou um ID de mensagem; envio não confirmado.')
    message=m.Message.objects.create(conversation=conversation,user=user,direction='out',body=body,external_id=external_id,result='accepted_by_api')
    conversation.status='waiting'; conversation.save()
    audit(user,message,'Mensagem aceita pela API oficial')
    return message
