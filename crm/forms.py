from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from . import models as m
from .permissions import scope, MANAGERS

class UserForm(forms.ModelForm):
    password=forms.CharField(label='Nova senha',widget=forms.PasswordInput,required=False,help_text='Obrigatória ao criar. Deixe vazia para manter a senha.')
    class Meta:
        model=m.User
        fields=['username','first_name','last_name','email','role','team','is_active','available','lead_limit','commission_percent']
    def clean_password(self):
        value=self.cleaned_data.get('password')
        if not self.instance.pk and not value: raise ValidationError('Defina uma senha.')
        if value: validate_password(value,self.instance)
        return value
    def save(self,commit=True):
        user=super().save(commit=False)
        if self.cleaned_data.get('password'): user.set_password(self.cleaned_data['password'])
        if commit: user.save()
        return user

FIELDS={
'customers':['first_name','last_name','phone','whatsapp','instagram','email','city','state','birthday','notes','consent'],
'leads':['customer','source','campaign','ad','owner','sdr','seller','stage','product','desired_model','capacity','color','condition','payment_method','wants_trade','estimated_down','budget','notes','next_followup','loss_reason','utm_source','utm_medium','utm_campaign','utm_content','utm_term'],
'activities':['customer','lead','kind','description','occurred_at'],
'products':['name','category','brand','model','generation','supplier','description','photo','active'],
'variants':['product','capacity','color','condition','imei','serial','price','promo_price','cost','commission_fixed'],
'inventory':['variant','minimum'],
'movements':['variant','kind','quantity','reason'],
'trades':['customer','brand','model','capacity','color','imei','physical_state','battery','face_id','true_tone','cameras','screen','housing','functioning','accessories','notes','appraisal','entry_value','repair_cost','resale_price','photo'],
'proposals':['customer','lead','seller','discount','payment_method','down_payment','trade','installments','valid_until','notes'],
'tasks':['title','description','owner','customer','lead','kind','due_at','priority','status'],
'goals':['name','user','team','kind','target','start','end'],
'commissions':['status'],
'campaigns':['name','source','investment'],
'investments':['campaign','date','amount','notes'],
'sources':['name'], 'loss-reasons':['name'], 'teams':['name'],
'stages':['name','position','kind','behavior','allows_sdr','qualifies_lead','color'],
'automations':['name','trigger','source','stage','action','delay_days','task_kind','active'],
'integrations':['channel','account_id','phone_id','enabled'],
'company':['name','logo','color','business_start','business_end','business_days','restrict_hours','followup_days','aftersale_days','sla_minutes'],
'scoring':['kind','points'],
'commission-rules':['name','category','product','percent','fixed','active'],
'inbox':['customer','lead','owner','channel','status'],
'reactivation-campaigns':['name','months','owner','notes']}

def build_form(module,model,user,data=None,files=None,instance=None,initial=None):
    if module=='users': return UserForm(data,files,instance=instance,initial=initial)
    model_class=model
    class ScopedForm(forms.ModelForm):
        class Meta:
            model=model_class
            fields=FIELDS[module]
        def clean(self):
            cleaned=super().clean()
            lead=cleaned.get('lead'); customer=cleaned.get('customer')
            if lead and customer and lead.customer_id!=customer.pk: self.add_error('lead','Este lead pertence a outro cliente.')
            if module=='leads':
                stage=cleaned.get('stage')
                if stage and stage.kind=='lost' and not cleaned.get('loss_reason'): self.add_error('loss_reason','Obrigatório para lead perdido.')
                if stage and stage.kind in {'won','after'} and (not self.instance.pk or not m.Sale.objects.filter(lead=self.instance,status='confirmed').exists()): self.add_error('stage','Registre uma venda primeiro.')
                campaign=cleaned.get('campaign')
                if campaign and campaign.source_id!=getattr(cleaned.get('source'),'pk',None): self.add_error('campaign','Campanha não pertence à origem selecionada.')
            if module=='integrations' and cleaned.get('channel')=='ai' and cleaned.get('enabled'): self.add_error('enabled','IA ainda não possui provedor implementado; mantenha desativada.')
            if module=='trades' and self.instance.status=='received': raise ValidationError('Aparelho recebido em venda não pode ter avaliação alterada.')
            for field in ['photo','logo']:
                if cleaned.get(field) and getattr(cleaned[field],'size',0)>5*1024*1024: self.add_error(field,'Limite de imagem: 5 MB.')
            if module=='goals':
                if cleaned.get('start') and cleaned.get('end') and cleaned['end']<cleaned['start']: self.add_error('end','Data anterior ao início.')
                if cleaned.get('target',0)<=0: self.add_error('target','Meta deve ser maior que zero.')
            if module=='company':
                for field in ['followup_days','aftersale_days']:
                    value=cleaned.get(field,'')
                    if not value or any(not x.strip().isdigit() or int(x)>3650 for x in value.split(',')): self.add_error(field,'Informe dias entre 0 e 3650 separados por vírgula.')
                if any(x not in '0123456' or len(x)!=1 for x in cleaned.get('business_days','').split(',')): self.add_error('business_days','Use dias de 0 a 6 separados por vírgula.')
                if cleaned.get('business_start') and cleaned.get('business_end') and cleaned['business_end']<=cleaned['business_start']: self.add_error('business_end','Fim deve ser posterior ao início.')
            if module in {'tasks','inbox'} and user.role_code not in MANAGERS: cleaned['owner']=user
            if module=='commissions':
                current=self.instance.status; nxt=cleaned.get('status')
                if current=='cancelled' or (current=='paid' and nxt!='paid'): raise ValidationError('Comissão cancelada/paga não pode ser reaberta.')
                if nxt=='paid' and self.instance.sale.payments.exclude(status='confirmed').exists(): raise ValidationError('Confirme todos os pagamentos antes de pagar a comissão.')
            return cleaned
    form=ScopedForm(data,files,instance=instance,initial=initial)
    for name,field in form.fields.items():
        if isinstance(field,forms.ModelChoiceField):
            relation=model._meta.get_field(name).remote_field.model
            field.queryset=scope(relation,user)
            if relation==m.User:
                field.queryset=m.User.objects.filter(is_active=True) if user.role_code in MANAGERS else m.User.objects.filter(pk=user.pk)
                if name=='sdr': field.queryset=field.queryset.filter(role='sdr')
                if name=='seller': field.queryset=field.queryset.filter(role='seller')
        if name in {'photo','logo'}: field.widget=forms.FileInput(attrs={'accept':'image/*'})
        if isinstance(field,forms.DateTimeField): field.widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'); field.input_formats=['%Y-%m-%dT%H:%M']
        elif isinstance(field,forms.DateField): field.widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')
        elif isinstance(field,forms.TimeField): field.widget=forms.TimeInput(attrs={'type':'time'},format='%H:%M')
        elif isinstance(field,forms.CharField) and isinstance(field.widget,forms.Textarea): field.widget.attrs['rows']=3
    if module=='leads' and user.role_code not in MANAGERS:
        for name in ['owner','sdr','seller']: form.fields.pop(name,None)
        if user.role_code=='sdr': form.fields['stage'].queryset=m.Stage.objects.filter(allows_sdr=True)
    if module=='proposals' and instance and instance.status in {'accepted','refused','expired'}:
        raise ValidationError('Proposta encerrada não pode ser editada.')
    return form

class ItemForm(forms.ModelForm):
    class Meta:
        model=m.ProposalItem
        fields=['variant','quantity','unit_price']
ItemFormSet=forms.inlineformset_factory(m.Proposal,m.ProposalItem,form=ItemForm,extra=1,can_delete=True,min_num=1,validate_min=True,max_num=50,validate_max=True)
