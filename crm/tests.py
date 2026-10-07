import hashlib, hmac, json
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from . import models as m, services as s
from .metrics import metrics, goal_value
from .permissions import scope, allowed
from .registry import REGISTRY

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CRMTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_crm',verbosity=0)
        cls.company=s.company(); cls.company.restrict_hours=False; cls.company.save()
        cls.admin=m.User.objects.create_user('admin',password='Strong-Test-123!',role='admin')
        cls.manager=m.User.objects.create_user('manager',password='Strong-Test-123!',role='manager')
        cls.bruna=m.User.objects.create_user('bruna',password='Strong-Test-123!',role='sdr',first_name='Bruna')
        cls.maria=m.User.objects.create_user('maria',password='Strong-Test-123!',role='sdr',first_name='Maria Clara')
        cls.seller=m.User.objects.create_user('seller',password='Strong-Test-123!',role='seller')
        cls.after=m.User.objects.create_user('after',password='Strong-Test-123!',role='after')
        cls.customer=m.Customer.objects.create(first_name='Cliente',last_name='Teste',phone='11999998888',consent=True,created_by=cls.admin)
        cls.other=m.Customer.objects.create(first_name='Oculto',phone='11911112222',created_by=cls.admin)
        cls.source=m.Source.objects.get(name='Instagram')
        cls.first=m.Stage.objects.first()
        cls.product=m.Product.objects.create(name='iPhone 17 Pro',model='17 Pro')
        cls.variant=m.Variant.objects.create(product=cls.product,price=10000,cost=7000)
        cls.stock=m.Inventory.objects.create(variant=cls.variant,quantity=10)
    def setUp(self): self.client.force_login(self.admin)
    def lead(self,**kwargs):
        params={'customer':self.customer,'source':self.source,'stage':self.first}; params.update(kwargs)
        return s.create_lead(m.Lead(**params),self.admin)
    def proposal(self,lead=None,quantity=1,price=10000,**kwargs):
        params={'customer':self.customer,'seller':self.seller,'lead':lead,'valid_until':timezone.localdate()+timedelta(days=7)}; params.update(kwargs)
        proposal=m.Proposal.objects.create(**params)
        m.ProposalItem.objects.create(proposal=proposal,variant=self.variant,quantity=quantity,unit_price=price)
        return proposal
    def test_login_and_logout(self):
        self.client.logout(); self.assertEqual(self.client.get('/leads/').status_code,302)
        self.assertEqual(self.client.post('/login/',{'username':'admin','password':'wrong'}).status_code,200)
        self.assertEqual(self.client.post('/login/',{'username':'admin','password':'Strong-Test-123!'}).status_code,302)
        self.assertEqual(self.client.post('/logout/').status_code,302)
    def test_login_throttle(self):
        self.client.logout()
        for _ in range(8): self.client.post('/login/',{'username':'admin','password':'wrong'})
        self.assertEqual(self.client.post('/login/',{'username':'admin','password':'wrong'}).status_code,429)
    def test_password_hashed_and_user_crud(self):
        response=self.client.post('/users/new/',{'username':'novo','first_name':'Novo','role':'seller','password':'Secure-Premium-2026!','lead_limit':50,'commission_percent':'2','is_active':'on'})
        self.assertEqual(response.status_code,302)
        user=m.User.objects.get(username='novo'); self.assertTrue(user.check_password('Secure-Premium-2026!')); self.assertNotEqual(user.password,'Secure-Premium-2026!')
    def test_customer_crud_consent(self):
        response=self.client.post('/customers/new/',{'first_name':'Ana','phone':'11999999999','consent':'on'})
        self.assertEqual(response.status_code,302); customer=m.Customer.objects.get(first_name='Ana'); self.assertIsNotNone(customer.consent_at)
        self.assertEqual(self.client.post(f'/customers/{customer.pk}/edit/',{'first_name':'Ana Maria','phone':'11999999999'}).status_code,302)
        customer.refresh_from_db(); self.assertIsNone(customer.consent_at)
        self.assertEqual(self.client.post(f'/customers/{customer.pk}/delete/').status_code,302); self.assertFalse(m.Customer.objects.filter(pk=customer.pk).exists())
    def test_lead_create_form_assigns(self):
        response=self.client.post('/leads/new/',{'customer':str(self.customer.pk),'source':str(self.source.pk),'stage':str(self.first.pk),'condition':'new','payment_method':'pix','estimated_down':'0','budget':'9000'})
        self.assertEqual(response.status_code,302); self.assertIsNotNone(m.Lead.objects.get().owner)
    def test_round_robin(self):
        leads=[self.lead() for _ in range(4)]
        self.assertEqual([x.owner_id for x in leads],[self.bruna.pk,self.maria.pk,self.bruna.pk,self.maria.pk])
        self.assertEqual(m.History.objects.filter(description__contains='automaticamente').count(),4)
    def test_distribution_limits_and_availability(self):
        self.bruna.available=False; self.bruna.save(); self.maria.lead_limit=1; self.maria.save()
        self.assertEqual(self.lead().owner_id,self.maria.pk); self.assertIsNone(self.lead().owner_id)
    def test_distribution_business_hours(self):
        self.company.restrict_hours=True; self.company.business_days=''; self.company.save()
        self.assertIsNone(self.lead().owner_id)
    def test_manual_owner_change_logged(self):
        lead=self.lead(); data={'customer':str(self.customer.pk),'source':str(self.source.pk),'stage':str(self.first.pk),'owner':self.seller.pk,'seller':self.seller.pk,'sdr':self.bruna.pk,'condition':'new','payment_method':'pix','estimated_down':'0','budget':'9000'}
        self.assertEqual(self.client.post(f'/leads/{lead.pk}/edit/',data).status_code,302)
        lead.refresh_from_db(); self.assertEqual(lead.owner_id,self.seller.pk); self.assertTrue(lead.history.filter(description__contains='Responsável alterado').exists())
    def test_loss_requires_reason(self):
        lead=self.lead(); lost=m.Stage.objects.get(kind='lost')
        with self.assertRaises(ValidationError): s.change_stage(lead,lost,self.admin)
        reason=m.LossReason.objects.first(); s.change_stage(lead,lost,self.admin,reason); lead.refresh_from_db(); self.assertEqual(lead.loss_reason,reason)
    def test_sdr_cannot_skip_to_negotiation(self):
        lead=self.lead(owner=self.bruna)
        with self.assertRaises(ValidationError): s.change_stage(lead,m.Stage.objects.get(position=6),self.bruna)
    def test_won_requires_sale(self):
        with self.assertRaises(ValidationError): s.change_stage(self.lead(),m.Stage.objects.get(kind='won'),self.admin)
    def test_kanban_json_persists(self):
        lead=self.lead(); stage=m.Stage.objects.get(position=2)
        response=self.client.post(f'/leads/{lead.pk}/stage/',{'stage':str(stage.pk)},HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code,200); lead.refresh_from_db(); self.assertEqual(lead.stage,stage)
    def test_sdr_transfer(self):
        lead=self.lead(owner=self.bruna); s.change_stage(lead,m.Stage.objects.get(position=3),self.bruna)
        self.client.force_login(self.bruna)
        self.assertEqual(self.client.post(f'/leads/{lead.pk}/transfer/',{'seller':self.seller.pk}).status_code,302)
        lead.refresh_from_db(); self.assertEqual(lead.owner,self.seller); self.assertEqual(lead.sdr,self.bruna if lead.sdr else None)
    def test_activity_scoring_and_contact(self):
        lead=self.lead(owner=self.bruna)
        s.record_activity(m.Activity(customer=self.customer,lead=lead,kind='payment',description='Pediu parcelamento'),self.bruna)
        lead.refresh_from_db(); self.assertEqual(lead.score,40); self.assertEqual(lead.temperature,'Morno'); self.assertIsNotNone(lead.first_contact_at)
    def test_task_form_and_complete(self):
        response=self.client.post('/tasks/new/',{'title':'Ligar amanhã','owner':self.bruna.pk,'customer':str(self.customer.pk),'due_at':'2026-11-01T10:00','kind':'call','priority':'high','status':'open'})
        self.assertEqual(response.status_code,302); task=m.Task.objects.get(title='Ligar amanhã')
        self.client.force_login(self.bruna); self.assertEqual(self.client.post(f'/tasks/{task.pk}/complete/').status_code,302); task.refresh_from_db(); self.assertEqual(task.status,'done')
    def test_followups_idempotent(self):
        lead=self.lead(owner=self.seller); proposal=self.proposal(lead)
        s.send_proposal(proposal,self.admin); count=m.Task.objects.count(); s.send_proposal(proposal,self.admin)
        self.assertEqual(m.Task.objects.count(),count); self.assertEqual(m.Task.objects.filter(automation_key__startswith=f'followup:{proposal.pk}').count(),3)
    def test_proposal_form_items(self):
        data={'customer':str(self.customer.pk),'seller':self.seller.pk,'discount':'500','payment_method':'pix','down_payment':'0','installments':'1','valid_until':(timezone.localdate()+timedelta(days=1)).isoformat(),'items-TOTAL_FORMS':'1','items-INITIAL_FORMS':'0','items-MIN_NUM_FORMS':'1','items-MAX_NUM_FORMS':'1000','items-0-variant':str(self.variant.pk),'items-0-quantity':'1','items-0-unit_price':'10000'}
        response=self.client.post('/proposals/new/',data); self.assertEqual(response.status_code,302); self.assertEqual(m.Proposal.objects.get().total,Decimal(9500))
    def test_bad_proposal_rolls_back(self):
        proposal=self.proposal(discount=Decimal(11000))
        with self.assertRaises(ValidationError): s.confirm_sale(proposal,self.admin)
        self.assertFalse(m.Sale.objects.exists()); self.stock.refresh_from_db(); self.assertEqual(self.stock.quantity,10)
    def test_sale_stock_commission_and_payments(self):
        proposal=self.proposal(self.lead(owner=self.seller),discount=500,installments=3,down_payment=500)
        sale=s.confirm_sale(proposal,self.admin); self.stock.refresh_from_db()
        self.assertEqual(sale.total,Decimal(9500)); self.assertEqual(self.stock.quantity,9); self.assertEqual(sale.commission.amount,Decimal(190))
        self.assertEqual(sale.payments.aggregate(n=__import__('django.db.models',fromlist=['Sum']).Sum('amount'))['n'],Decimal(9500))
        self.assertEqual(m.Task.objects.filter(automation_key__startswith=f'after:{sale.pk}').count(),5)
    def test_sale_stock_failure_atomic(self):
        proposal=self.proposal(quantity=11)
        with self.assertRaises(ValidationError): s.confirm_sale(proposal,self.admin)
        self.assertFalse(m.Sale.objects.exists()); self.assertFalse(m.Commission.objects.exists()); self.stock.refresh_from_db(); self.assertEqual(self.stock.quantity,10)
    def test_duplicate_sale_rejected(self):
        proposal=self.proposal(); s.confirm_sale(proposal,self.admin)
        with self.assertRaises(ValidationError): s.confirm_sale(proposal,self.admin)
        self.assertEqual(m.Sale.objects.count(),1)
    def test_sale_cancellation_restock(self):
        sale=s.confirm_sale(self.proposal(),self.admin); s.cancel_sale(sale,self.admin)
        self.stock.refresh_from_db(); sale.refresh_from_db(); self.assertEqual(self.stock.quantity,10); self.assertEqual(sale.status,'cancelled'); self.assertEqual(m.Commission.objects.get(sale=sale).status,'cancelled')
    def test_commission_rule_and_payment_gate(self):
        m.CommissionRule.objects.create(name='Categoria',category='Smartphone',percent=3)
        m.CommissionRule.objects.create(name='Produto',product=self.product,percent=1,fixed=50)
        sale=s.confirm_sale(self.proposal(),self.admin); self.assertEqual(sale.commission.amount,Decimal(150))
        response=self.client.post(f'/commissions/{sale.commission.pk}/edit/',{'status':'paid'}); self.assertEqual(response.status_code,200)
        payment=sale.payments.first(); self.client.post(f'/sales/{sale.pk}/payment/',{'payment':str(payment.pk)})
        self.assertEqual(self.client.post(f'/commissions/{sale.commission.pk}/edit/',{'status':'paid'}).status_code,302)
    def test_inventory_reservation_rules(self):
        s.move_stock(self.variant,'reserve',8,self.admin,'Reserva')
        with self.assertRaises(ValidationError): s.move_stock(self.variant,'out',3,self.admin,'Saída')
        s.move_stock(self.variant,'release',2,self.admin,'Liberação'); self.stock.refresh_from_db(); self.assertEqual(self.stock.available,4)
    def test_trade_enters_inventory(self):
        device=m.UsedDevice.objects.create(customer=self.customer,model='iPhone 13',capacity='128 GB',color='Preto',imei='123456789123456',physical_state='Bom',battery=86,entry_value=1500,repair_cost=200,resale_price=2500)
        sale=s.confirm_sale(self.proposal(trade=device),self.admin); device.refresh_from_db()
        self.assertEqual(device.total_cost,1700); self.assertEqual(device.margin,800); self.assertEqual(device.status,'received'); self.assertEqual(device.stock_variant.inventory.quantity,1); self.assertEqual(sale.payments.first().amount,8500)
    def test_goal_computed_from_sales(self):
        goal=m.Goal.objects.create(name='Meta',user=self.seller,kind='revenue',target=100000,start=timezone.localdate(),end=timezone.localdate())
        self.assertEqual(goal_value(goal),0); s.confirm_sale(self.proposal(),self.admin); self.assertEqual(goal_value(goal),10000)
    def test_metrics_no_fabricated_finance(self):
        self.lead(owner=self.seller); s.confirm_sale(self.proposal(),self.admin)
        data=metrics(self.admin,{'period':'today'}); self.assertEqual(data['revenue'],10000); self.assertEqual(dict(data['totals'])['CAC'],'Dados insuficientes')
    def test_scope_sdr_other_lead_forbidden(self):
        visible=self.lead(owner=self.bruna); hidden=self.lead(customer=self.other,owner=self.maria)
        self.client.force_login(self.bruna); self.assertEqual(self.client.get(f'/leads/{visible.pk}/').status_code,200); self.assertEqual(self.client.get(f'/leads/{hidden.pk}/').status_code,404)
        self.assertEqual(self.client.post(f'/leads/{hidden.pk}/stage/',{'stage':str(self.first.pk)}).status_code,404)
        self.assertNotContains(self.client.get('/search/?q=Oculto'),'Oculto ·')
    def test_scope_seller_cannot_access_other_sales(self):
        sale=s.confirm_sale(self.proposal(),self.admin)
        other_seller=m.User.objects.create_user('other_seller',role='seller'); self.client.force_login(other_seller)
        self.assertEqual(self.client.get(f'/sales/{sale.pk}/').status_code,404); self.assertEqual(self.client.get(f'/payments/{sale.payments.first().pk}/').status_code,404)
    def test_sdr_finance_and_admin_forbidden(self):
        self.client.force_login(self.bruna)
        for url in ['/reports/','/sales/','/commissions/','/settings/','/users/new/','/inventory/']: self.assertEqual(self.client.get(url).status_code,403,url)
    def test_sdr_cannot_forge_owner(self):
        self.client.force_login(self.bruna)
        customer=m.Customer.objects.create(first_name='Próprio',phone='11988887777',created_by=self.bruna)
        response=self.client.post('/leads/new/',{'customer':str(customer.pk),'source':str(self.source.pk),'stage':str(self.first.pk),'owner':self.maria.pk,'condition':'new','payment_method':'pix','estimated_down':0,'budget':0})
        self.assertEqual(response.status_code,302); self.assertEqual(m.Lead.objects.get().owner,self.bruna)
    def test_after_sales_scope(self):
        self.client.force_login(self.after); self.assertEqual(self.client.get(f'/customers/{self.customer.pk}/').status_code,404)
        self.client.force_login(self.admin); s.confirm_sale(self.proposal(),self.admin); self.client.force_login(self.after)
        self.assertEqual(self.client.get(f'/customers/{self.customer.pk}/').status_code,200); self.assertEqual(self.client.get('/sales/').status_code,403)
    def test_filters_and_export(self):
        lead=self.lead(owner=self.bruna,score=80)
        response=self.client.get('/leads/',{'owner':self.bruna.pk,'temperature':'hot'}); self.assertContains(response,'Cliente Teste')
        self.assertNotContains(self.client.get('/leads/',{'temperature':'cold'}),'Cliente Teste')
        csv=self.client.get('/leads/?export=csv'); self.assertEqual(csv['Content-Type'],'text/csv; charset=utf-8'); self.assertIn('Cliente Teste',csv.content.decode())
    def test_global_imei_and_sale_number_search(self):
        self.variant.imei='987654321098765'; self.variant.save(); self.assertContains(self.client.get('/search/?q=987654321098765'),'iPhone 17 Pro')
        self.variant.imei=''; self.variant.save(); sale=s.confirm_sale(self.proposal(),self.admin)
        self.assertContains(self.client.get('/search/?q=VEN-'+str(sale.pk)[:8].upper()),'VEN-'+str(sale.pk)[:8].upper())
    def test_invalid_filter_does_not_crash(self): self.assertEqual(self.client.get('/leads/?owner=invalid').status_code,200)
    def test_csv_formula_injection(self):
        self.customer.first_name='=SUM(1,1)'; self.customer.save()
        self.assertIn("'=SUM",self.client.get('/customers/?export=csv').content.decode())
    def test_favorite_filter_saved(self):
        self.client.post('/leads/filters/save/',{'name':'Quentes','temperature':'hot'}); self.assertEqual(m.SavedFilter.objects.get().params,{'temperature':'hot'})
    def test_lgpd_anonymization(self):
        lead=self.lead(); activity=m.Activity(customer=self.customer,lead=lead,kind='note',description='Dados pessoais'); s.record_activity(activity,self.admin)
        s.anonymize(self.customer,self.admin); self.customer.refresh_from_db(); activity.refresh_from_db()
        self.assertEqual(self.customer.phone,''); self.assertFalse(self.customer.consent); self.assertIsNotNone(self.customer.anonymized_at); self.assertNotIn('Dados pessoais',activity.description); self.assertTrue(m.Lead.objects.filter(pk=lead.pk).exists())
    def test_delete_customer_with_commercial_history_protected(self):
        self.lead(); self.client.post(f'/customers/{self.customer.pk}/delete/'); self.assertTrue(m.Customer.objects.filter(pk=self.customer.pk).exists())
    def test_whatsapp_open_not_message(self):
        lead=self.lead(); response=self.client.post(f'/leads/{lead.pk}/whatsapp/')
        self.assertEqual(response['Location'],'https://wa.me/5511999998888'); self.assertEqual(m.Message.objects.count(),0); self.assertTrue(lead.history.filter(description__contains='não confirmado').exists())
    def test_unconfigured_integrations_no_fake_messages(self):
        conv=m.Conversation.objects.create(customer=self.customer,owner=self.seller,channel='whatsapp')
        from .integrations import send_message
        with self.assertRaises(ValidationError): send_message(conv,'Olá',self.seller)
        self.assertFalse(m.Message.objects.exists())
    def test_csrf_required(self):
        client=Client(enforce_csrf_checks=True); client.force_login(self.admin)
        self.assertEqual(client.post('/customers/new/',{'first_name':'X','phone':'1'}).status_code,403)
    def test_automations_notifications_idempotent(self):
        lead=self.lead(); m.Lead.objects.filter(pk=lead.pk).update(created_at=timezone.now()-timedelta(minutes=20)); s.run_scheduled(); count=m.Notification.objects.count(); s.run_scheduled(); self.assertEqual(m.Notification.objects.count(),count)
    def test_custom_automation(self):
        m.Automation.objects.create(name='Contato Instagram',trigger='new_lead',source=self.source,delay_days=0,action='task',task_kind='whatsapp')
        lead=self.lead(); self.assertTrue(m.Task.objects.filter(lead=lead,title='Contato Instagram').exists())
    @override_settings(LEAD_API_KEY='secure-test-key')
    def test_lead_capture_api(self):
        self.assertEqual(self.client.post('/api/leads/',data=json.dumps({'name':'API','phone':'11999990000'}),content_type='application/json').status_code,401)
        response=self.client.post('/api/leads/',data=json.dumps({'name':'API','phone':'11999990000','utm_campaign':'launch'}),content_type='application/json',HTTP_X_API_KEY='secure-test-key')
        self.assertEqual(response.status_code,201); self.assertEqual(m.Lead.objects.get().utm_campaign,'launch')
    @override_settings(META_APP_SECRET='test-secret',META_VERIFY_TOKEN='verify')
    def test_webhook_signature_and_idempotency(self):
        m.Integration.objects.filter(channel='whatsapp').update(enabled=True,phone_id='phone-id')
        payload={'entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'phone-id'},'contacts':[{'wa_id':'5511999912345','profile':{'name':'Contato real'}}],'messages':[{'id':'wamid.123','from':'5511999912345','type':'text','text':{'body':'Gostaria de um iPhone'}}]}}]}]}
        body=json.dumps(payload); signature='sha256='+hmac.new(b'test-secret',body.encode(),hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post('/webhooks/meta/',body,content_type='application/json').status_code,403)
        for _ in range(2): self.assertEqual(self.client.post('/webhooks/meta/',body,content_type='application/json',HTTP_X_HUB_SIGNATURE_256=signature).status_code,200)
        self.assertEqual(m.Message.objects.count(),1); self.assertEqual(m.Customer.objects.filter(first_name='Contato real').count(),1)
        self.assertEqual(self.client.get('/webhooks/meta/',{'hub.mode':'subscribe','hub.verify_token':'verify','hub.challenge':'123'}).content,b'123')
    def test_self_deactivation_rejected(self):
        response=self.client.post(f'/users/{self.admin.pk}/edit/',{'username':'admin','role':'admin','lead_limit':50,'commission_percent':2})
        self.assertEqual(response.status_code,200); self.admin.refresh_from_db(); self.assertTrue(self.admin.is_active)
    def test_all_modules_and_new_forms_render(self):
        from .forms import FIELDS
        for module in REGISTRY:
            self.assertEqual(self.client.get(f'/{module}/').status_code,200,module)
            if module in FIELDS or module=='users': self.assertEqual(self.client.get(f'/{module}/new/').status_code,200,module)
        for url in ['/dashboard/','/pipeline/','/reports/','/settings/','/aftercare/','/reactivation/','/privacy/']: self.assertEqual(self.client.get(url).status_code,200,url)
    @override_settings(LEAD_API_KEY='secure-test-key')
    def test_api_reuses_normalized_customer(self):
        count=m.Customer.objects.count()
        response=self.client.post('/api/leads/',data=json.dumps({'name':'Cliente','phone':'+55 (11) 99999-8888'}),content_type='application/json',HTTP_X_API_KEY='secure-test-key')
        self.assertEqual(response.status_code,201); self.assertEqual(m.Customer.objects.count(),count); self.assertEqual(m.Lead.objects.get().customer,self.customer)
    def test_goal_reached_notification(self):
        goal=m.Goal.objects.create(name='Meta atingida',user=self.seller,kind='revenue',target=5000,start=timezone.localdate(),end=timezone.localdate())
        s.confirm_sale(self.proposal(),self.admin); s.run_scheduled(); s.run_scheduled()
        self.assertEqual(m.Notification.objects.filter(key=f'goal:{goal.pk}:{self.seller.pk}').count(),1)
    def test_sla_uses_company_setting(self):
        lead=self.lead(); m.Lead.objects.filter(pk=lead.pk).update(created_at=timezone.now()-timedelta(minutes=10)); lead.refresh_from_db()
        self.assertEqual(lead.sla,'Estourado'); self.company.sla_minutes=15; self.company.save(); self.assertEqual(lead.sla,'No prazo')
    def test_authenticated_photo_upload_and_scope(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from io import BytesIO
        from tempfile import TemporaryDirectory
        data=BytesIO(); Image.new('RGB',(8,8),color='blue').save(data,format='PNG')
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            device=m.UsedDevice.objects.create(customer=self.customer,model='iPhone 13',capacity='128 GB',color='Preto',imei='111111111111111',physical_state='Bom',battery=90)
            response=self.client.post(f'/trades/{device.pk}/photo/',{'image':SimpleUploadedFile('device.png',data.getvalue(),content_type='image/png')})
            self.assertEqual(response.status_code,302); photo=device.photos.get(); url=f'/trades/{device.pk}/images/{photo.pk}/'
            self.assertEqual(self.client.get(url).status_code,200)
            self.client.force_login(self.seller); self.assertEqual(self.client.get(url).status_code,404)
            self.client.logout(); self.assertEqual(self.client.get(url).status_code,302)
            self.client.force_login(self.admin); self.assertEqual(self.client.post(f'/trades/{device.pk}/photo-remove/',{'photo':str(photo.pk)}).status_code,302); self.assertFalse(device.photos.exists())
    def test_marketing_cac_and_roi_from_real_spend(self):
        campaign=m.Campaign.objects.create(name='Campanha real',source=self.source)
        lead=self.lead(campaign=campaign); s.confirm_sale(self.proposal(lead),self.admin)
        self.assertEqual(dict(metrics(self.admin,{'period':'today'})['totals'])['CAC'],'Dados insuficientes')
        m.MarketingSpend.objects.create(campaign=campaign,date=timezone.localdate(),amount=1000)
        values=dict(metrics(self.admin,{'period':'today'})['totals']); self.assertEqual(values['CAC'],'R$ 1000.00'); self.assertEqual(values['ROI'],'900.0%')
    def test_roles_are_relational_and_protected(self):
        from django.db.models.deletion import ProtectedError
        self.assertEqual(self.seller.role.code,'seller'); self.assertEqual(self.seller.role_code,'seller')
        with self.assertRaises(ProtectedError): self.seller.role.delete()
    def test_pipeline_rules_survive_renamed_reordered_stages(self):
        stage=m.Stage.objects.get(behavior='proposal'); stage.name='Orçamento apresentado'; stage.position=50; stage.save()
        lead=self.lead(owner=self.seller); proposal=self.proposal(lead); s.send_proposal(proposal,self.admin)
        lead.refresh_from_db(); self.assertEqual(lead.stage_id,stage.pk); self.assertEqual(m.Task.objects.filter(automation_key__startswith=f'followup:{proposal.pk}').count(),3)
    def test_waiting_distribution_does_not_duplicate_history(self):
        m.User.objects.filter(role='sdr').update(available=False)
        lead=self.lead(); count=lead.history.count(); s.run_scheduled(); s.run_scheduled(); self.assertEqual(lead.history.count(),count)
    def test_automatic_proposal_expiry_is_audited(self):
        proposal=self.proposal(valid_until=timezone.localdate()-timedelta(days=1)); s.run_scheduled(); proposal.refresh_from_db()
        self.assertEqual(proposal.status,'expired'); self.assertTrue(m.AuditLog.objects.filter(object_id=str(proposal.pk),action='Expiração automática').exists())
    def test_assigned_proposal_connects_seller_client_and_sale(self):
        lead=self.lead(owner=self.bruna); proposal=self.proposal(lead)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(f'/customers/{self.customer.pk}/').status_code,200)
        self.assertEqual(self.client.get(f'/leads/{lead.pk}/').status_code,200)
        response=self.client.post(f'/proposals/{proposal.pk}/sell/')
        self.assertEqual(response.status_code,302); lead.refresh_from_db(); self.assertEqual(lead.owner,self.seller); self.assertEqual(lead.sdr,self.bruna)
    def test_sdr_lead_goal_retains_transferred_assignments(self):
        lead=self.lead(owner=self.bruna); s.change_stage(lead,m.Stage.objects.get(name='Qualificado'),self.bruna)
        self.client.post(f'/leads/{lead.pk}/transfer/',{'seller':self.seller.pk})
        goal=m.Goal.objects.create(name='Leads recebidos',user=self.bruna,kind='leads',target=10,start=timezone.localdate(),end=timezone.localdate())
        self.assertEqual(goal_value(goal),1)
