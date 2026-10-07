import uuid, re
from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone

def normalized_phone(value):
    phone=re.sub(r'\D','',value or '')
    return '55'+phone if len(phone) in {10,11} else phone

MONEY={'max_digits':12,'decimal_places':2,'default':0,'validators':[MinValueValidator(0)]}
ROLES=[('admin','Administrador'),('manager','Gestor'),('sdr','SDR'),('seller','Vendedor'),('after','Pós-venda')]
PAYMENTS=[('pix','PIX'),('cash','Dinheiro'),('credit','Cartão de crédito'),('debit','Cartão de débito'),('transfer','Transferência'),('finance','Financiamento'),('other','Outros')]
class Base(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    created_at=models.DateTimeField(auto_now_add=True,db_index=True)
    updated_at=models.DateTimeField(auto_now=True)
    is_demo=models.BooleanField(default=False,editable=False)
    class Meta: abstract=True
class Role(Base):
    code=models.CharField(max_length=20,unique=True,choices=ROLES)
    name=models.CharField(max_length=80)
    def __str__(self): return self.name
class Team(Base):
    name=models.CharField('Nome',max_length=120)
    def __str__(self): return self.name
class User(AbstractUser):
    REQUIRED_FIELDS=['email','role']
    role=models.ForeignKey(Role,to_field='code',on_delete=models.PROTECT,verbose_name='Perfil',default='sdr')
    team=models.ForeignKey(Team,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Equipe')
    available=models.BooleanField('Disponível para leads',default=True)
    lead_limit=models.PositiveIntegerField('Limite de leads ativos',default=50)
    commission_percent=models.DecimalField('Comissão (%)',max_digits=5,decimal_places=2,default=2,validators=[MinValueValidator(0),MaxValueValidator(100)])
    is_demo=models.BooleanField(default=False)
    def __init__(self,*args,**kwargs):
        if isinstance(kwargs.get('role'),str): kwargs['role_id']=kwargs.pop('role')
        super().__init__(*args,**kwargs)
    @property
    def role_code(self): return self.role_id
    def get_role_display(self): return dict(ROLES).get(self.role_id,self.role_id)
    def __str__(self): return self.get_full_name() or self.username
class Source(Base):
    name=models.CharField('Origem',max_length=100,unique=True)
    def __str__(self): return self.name
class Campaign(Base):
    name=models.CharField('Campanha',max_length=150)
    source=models.ForeignKey(Source,on_delete=models.PROTECT,verbose_name='Origem')
    investment=models.DecimalField('Investimento',null=True,blank=True,**{k:v for k,v in MONEY.items() if k!='default'})
    def __str__(self): return self.name
class Customer(Base):
    first_name=models.CharField('Nome',max_length=100)
    last_name=models.CharField('Sobrenome',max_length=100,blank=True)
    phone=models.CharField('Telefone',max_length=25,blank=True)
    contact_key=models.CharField(max_length=20,blank=True,db_index=True,editable=False)
    whatsapp=models.CharField('WhatsApp',max_length=25,blank=True)
    instagram=models.CharField('Instagram',max_length=100,blank=True)
    email=models.EmailField('E-mail',blank=True)
    city=models.CharField('Cidade',max_length=100,blank=True)
    state=models.CharField('Estado',max_length=2,blank=True)
    birthday=models.DateField('Nascimento',null=True,blank=True)
    notes=models.TextField('Observações',blank=True)
    consent=models.BooleanField('Consentimento para marketing',default=False)
    consent_at=models.DateTimeField(null=True,blank=True,editable=False)
    anonymized_at=models.DateTimeField(null=True,blank=True,editable=False)
    created_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,editable=False)
    def save(self,*args,**kwargs):
        self.contact_key=normalized_phone(self.whatsapp or self.phone)
        if kwargs.get('update_fields') and ({'phone','whatsapp'} & set(kwargs['update_fields'])): kwargs['update_fields']=set(kwargs['update_fields'])|{'contact_key'}
        super().save(*args,**kwargs)
    def clean(self):
        from django.core.exceptions import ValidationError
        for field in ['phone','whatsapp']:
            value=getattr(self,field)
            if value and not 10<=len(re.sub(r'\D','',value))<=15: raise ValidationError({field:'Informe um telefone com DDD válido.'})
    def __str__(self): return f'{self.first_name} {self.last_name}'.strip()
class Stage(Base):
    name=models.CharField('Etapa',max_length=100)
    position=models.PositiveIntegerField('Posição',unique=True)
    behavior=models.CharField('Função da etapa',max_length=20,choices=[('standard','Padrão'),('new','Entrada de lead'),('proposal','Proposta enviada'),('negotiation','Negociação'),('payment','Pagamento')],default='standard')
    allows_sdr=models.BooleanField('SDR pode mover para esta etapa',default=False)
    qualifies_lead=models.BooleanField('Qualifica o lead',default=False)
    kind=models.CharField('Tipo',max_length=15,choices=[('open','Aberta'),('won','Venda'),('after','Pós-venda'),('lost','Perdida')],default='open')
    color=models.CharField('Cor',max_length=7,default='#6558f5',validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$','Informe uma cor hexadecimal, por exemplo #6558f5.')])
    class Meta:
        ordering=['position']
        constraints=[models.UniqueConstraint(fields=['behavior'],condition=~Q(behavior='standard'),name='single_stage_behavior')]
    def __str__(self): return self.name
class LossReason(Base):
    name=models.CharField('Motivo',max_length=150,unique=True)
    def __str__(self): return self.name
class Product(Base):
    name=models.CharField('Produto',max_length=150)
    category=models.CharField('Categoria',max_length=100,default='Smartphone')
    brand=models.CharField('Marca',max_length=80,default='Apple')
    model=models.CharField('Modelo',max_length=100)
    generation=models.CharField('Geração',max_length=50,blank=True)
    supplier=models.CharField('Fornecedor',max_length=150,blank=True)
    description=models.TextField('Descrição',blank=True)
    photo=models.ImageField('Foto',upload_to='products/',blank=True)
    active=models.BooleanField('Ativo',default=True)
    def __str__(self): return self.name
class Variant(Base):
    product=models.ForeignKey(Product,on_delete=models.PROTECT,related_name='variants',verbose_name='Produto')
    capacity=models.CharField('Capacidade',max_length=50,default='128 GB')
    color=models.CharField('Cor',max_length=50,default='Preto')
    condition=models.CharField('Condição',max_length=10,choices=[('new','Novo'),('used','Usado')],default='new')
    imei=models.CharField('IMEI',max_length=30,blank=True)
    serial=models.CharField('Serial',max_length=80,blank=True)
    price=models.DecimalField('Preço',**MONEY)
    promo_price=models.DecimalField('Preço promocional',null=True,blank=True,**{k:v for k,v in MONEY.items() if k!='default'})
    cost=models.DecimalField('Custo',**MONEY)
    commission_fixed=models.DecimalField('Comissão fixa por unidade',null=True,blank=True,**{k:v for k,v in MONEY.items() if k!='default'})
    class Meta:
        constraints=[models.UniqueConstraint(fields=['imei'],condition=~Q(imei=''),name='unique_variant_imei'),models.UniqueConstraint(fields=['serial'],condition=~Q(serial=''),name='unique_variant_serial')]
    @property
    def selling_price(self): return self.promo_price if self.promo_price is not None else self.price
    def __str__(self): return f'{self.product} · {self.capacity} · {self.color}'
class Inventory(Base):
    variant=models.OneToOneField(Variant,on_delete=models.PROTECT,related_name='inventory',verbose_name='Variante')
    quantity=models.PositiveIntegerField('Em estoque',default=0)
    reserved=models.PositiveIntegerField('Reservado',default=0)
    minimum=models.PositiveIntegerField('Estoque mínimo',default=2)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gte=models.F('reserved')),name='stock_reservation_limit')]
    @property
    def sold(self): return SaleItem.objects.filter(variant=self.variant,sale__status='confirmed').aggregate(n=models.Sum('quantity'))['n'] or 0
    @property
    def low_stock(self): return self.available<=self.minimum
    @property
    def available(self): return self.quantity-self.reserved
    def __str__(self): return str(self.variant)
class Lead(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='leads',verbose_name='Cliente')
    source=models.ForeignKey(Source,on_delete=models.PROTECT,verbose_name='Origem')
    campaign=models.ForeignKey(Campaign,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Campanha')
    ad=models.CharField('Anúncio',max_length=150,blank=True)
    owner=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name='leads',verbose_name='Responsável')
    sdr=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='sdr_leads',verbose_name='SDR')
    seller=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='seller_leads',verbose_name='Vendedor')
    stage=models.ForeignKey(Stage,on_delete=models.PROTECT,verbose_name='Etapa')
    product=models.ForeignKey(Product,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Produto de interesse')
    desired_model=models.CharField('Modelo desejado',max_length=100,blank=True)
    capacity=models.CharField('Capacidade',max_length=50,blank=True)
    color=models.CharField('Cor',max_length=50,blank=True)
    condition=models.CharField('Condição',max_length=10,choices=[('new','Novo'),('used','Usado')],default='new')
    payment_method=models.CharField('Pagamento desejado',max_length=20,choices=PAYMENTS,default='pix')
    wants_trade=models.BooleanField('Deseja dar aparelho na troca',default=False)
    estimated_down=models.DecimalField('Entrada estimada',**MONEY)
    budget=models.DecimalField('Orçamento',**MONEY)
    notes=models.TextField('Observações',blank=True)
    score=models.PositiveIntegerField(default=0,validators=[MaxValueValidator(100)])
    loss_reason=models.ForeignKey(LossReason,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Motivo de perda')
    qualified_at=models.DateTimeField(null=True,blank=True,editable=False)
    first_contact_at=models.DateTimeField(null=True,blank=True,editable=False)
    last_interaction=models.DateTimeField(null=True,blank=True,editable=False)
    next_followup=models.DateTimeField(null=True,blank=True,verbose_name='Próximo follow-up')
    stage_changed_at=models.DateTimeField(default=timezone.now,editable=False)
    utm_source=models.CharField(max_length=150,blank=True)
    utm_medium=models.CharField(max_length=150,blank=True)
    utm_campaign=models.CharField(max_length=150,blank=True)
    utm_content=models.CharField(max_length=150,blank=True)
    utm_term=models.CharField(max_length=150,blank=True)
    @property
    def temperature(self): return 'Quente' if self.score>60 else 'Morno' if self.score>30 else 'Frio'
    @property
    def sla(self):
        if self.first_contact_at: return 'Atendido'
        minutes=(timezone.now()-self.created_at).total_seconds()/60
        config=Company.objects.first(); limit=config.sla_minutes if config else 5
        return 'Estourado' if minutes>limit else 'Atenção' if minutes>limit*.8 else 'No prazo'
    def __str__(self): return f'{self.customer} · {self.stage}'
class History(Base):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name='history')
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
    description=models.TextField()
class Activity(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='activities',verbose_name='Cliente')
    lead=models.ForeignKey(Lead,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Lead')
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,editable=False)
    kind=models.CharField('Tipo',max_length=30,choices=[('call','Ligação'),('whatsapp','WhatsApp registrado'),('instagram','Instagram registrado'),('note','Observação'),('meeting','Reunião'),('price','Pediu preço'),('availability','Pediu disponibilidade'),('payment','Pediu pagamento'),('purchase','Enviou dados de compra')],default='note')
    description=models.TextField('Registro')
    occurred_at=models.DateTimeField('Data/hora',default=timezone.now)
class Task(Base):
    title=models.CharField('Título',max_length=200)
    description=models.TextField('Descrição',blank=True)
    owner=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='Responsável')
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Cliente')
    lead=models.ForeignKey(Lead,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Lead')
    kind=models.CharField('Tipo',max_length=30,choices=[('call','Ligar'),('whatsapp','Enviar WhatsApp'),('instagram','Responder Instagram'),('proposal','Enviar proposta'),('payment','Confirmar pagamento'),('after','Pós-venda'),('review','Solicitar avaliação'),('reactivate','Reativar cliente'),('stock','Verificar estoque'),('return','Retornar cliente')],default='return')
    due_at=models.DateTimeField('Data e hora')
    priority=models.CharField('Prioridade',max_length=10,choices=[('high','Alta'),('medium','Média'),('low','Baixa')],default='medium')
    status=models.CharField('Status',max_length=10,choices=[('open','Aberta'),('done','Concluída'),('cancelled','Cancelada')],default='open')
    automation_key=models.CharField(max_length=200,null=True,blank=True,unique=True,editable=False)
    @property
    def overdue(self): return self.status=='open' and self.due_at<timezone.now()
    def __str__(self): return self.title
class Conversation(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,verbose_name='Cliente')
    lead=models.ForeignKey(Lead,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Lead')
    owner=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Responsável')
    channel=models.CharField('Canal',max_length=20,choices=[('whatsapp','WhatsApp'),('instagram','Instagram')])
    status=models.CharField('Status',max_length=20,choices=[('new','Nova'),('unanswered','Não respondida'),('active','Em andamento'),('waiting','Aguardando resposta'),('closed','Encerrada')],default='new')
    external_id=models.CharField(max_length=150,blank=True)
    def __str__(self): return f'{self.customer} · {self.get_channel_display()}'
class Message(Base):
    conversation=models.ForeignKey(Conversation,on_delete=models.CASCADE,related_name='messages')
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
    direction=models.CharField(max_length=10,choices=[('in','Recebida'),('out','Enviada')])
    body=models.TextField()
    external_id=models.CharField(max_length=200,unique=True,null=True)
    result=models.CharField(max_length=80,default='confirmed')
class UsedDevice(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,verbose_name='Cliente')
    brand=models.CharField('Marca',max_length=80,default='Apple')
    model=models.CharField('Modelo',max_length=100)
    capacity=models.CharField('Capacidade',max_length=50)
    color=models.CharField('Cor',max_length=50)
    imei=models.CharField('IMEI',max_length=30,unique=True)
    physical_state=models.CharField('Estado físico',max_length=150)
    battery=models.PositiveIntegerField('Saúde da bateria (%)',validators=[MaxValueValidator(100)])
    face_id=models.BooleanField('Face ID funcional',default=True)
    true_tone=models.BooleanField('True Tone funcional',default=True)
    cameras=models.BooleanField('Câmeras funcionais',default=True)
    screen=models.BooleanField('Tela íntegra',default=True)
    housing=models.BooleanField('Carcaça íntegra',default=True)
    functioning=models.BooleanField('Funcionamento geral',default=True)
    accessories=models.CharField('Acessórios',max_length=200,blank=True)
    notes=models.TextField('Observações',blank=True)
    appraisal=models.DecimalField('Avaliação',**MONEY)
    entry_value=models.DecimalField('Valor de entrada',**MONEY)
    repair_cost=models.DecimalField('Custos previstos',**MONEY)
    resale_price=models.DecimalField('Revenda estimada',**MONEY)
    photo=models.ImageField('Foto',upload_to='trades/',blank=True)
    stock_variant=models.OneToOneField(Variant,on_delete=models.PROTECT,null=True,blank=True,editable=False)
    status=models.CharField(max_length=20,default='evaluated',choices=[('evaluated','Avaliado'),('received','Recebido')],editable=False)
    @property
    def total_cost(self): return self.entry_value+self.repair_cost
    @property
    def margin(self): return self.resale_price-self.total_cost
    def __str__(self): return f'{self.model} · {self.imei}'
class Proposal(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,verbose_name='Cliente')
    lead=models.ForeignKey(Lead,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Lead')
    seller=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='Vendedor')
    status=models.CharField('Status',max_length=20,choices=[('draft','Rascunho'),('sent','Enviada'),('viewed','Visualizada'),('negotiating','Em negociação'),('accepted','Aceita'),('refused','Recusada'),('expired','Expirada')],default='draft')
    discount=models.DecimalField('Desconto',**MONEY)
    payment_method=models.CharField('Forma de pagamento',choices=PAYMENTS,max_length=20,default='pix')
    down_payment=models.DecimalField('Entrada',**MONEY)
    trade=models.ForeignKey(UsedDevice,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Troca')
    installments=models.PositiveIntegerField('Parcelas',default=1,validators=[MinValueValidator(1),MaxValueValidator(48)])
    valid_until=models.DateField('Validade')
    notes=models.TextField('Observações',blank=True)
    @property
    def total(self): return sum((i.quantity*i.unit_price for i in self.items.all()),Decimal(0))-self.discount
    @property
    def balance(self): return self.total-self.down_payment-(self.trade.entry_value if self.trade else 0)
    def __str__(self): return f'PROP-{str(self.id)[:8].upper()} · {self.customer}'
class ProposalItem(Base):
    proposal=models.ForeignKey(Proposal,on_delete=models.CASCADE,related_name='items')
    variant=models.ForeignKey(Variant,on_delete=models.PROTECT,verbose_name='Produto/variante')
    quantity=models.PositiveIntegerField('Quantidade',default=1,validators=[MinValueValidator(1)])
    unit_price=models.DecimalField('Preço unitário',**MONEY)
    class Meta: constraints=[models.CheckConstraint(condition=Q(quantity__gt=0),name='proposal_qty_positive')]
class Sale(Base):
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='sales',verbose_name='Cliente')
    lead=models.ForeignKey(Lead,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Lead')
    proposal=models.OneToOneField(Proposal,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Proposta')
    seller=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='Vendedor')
    discount=models.DecimalField('Desconto',**MONEY)
    payment_method=models.CharField('Forma de pagamento',choices=PAYMENTS,max_length=20,default='pix')
    down_payment=models.DecimalField('Entrada',**MONEY)
    trade=models.OneToOneField(UsedDevice,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Troca')
    installments=models.PositiveIntegerField('Parcelas',default=1,validators=[MinValueValidator(1),MaxValueValidator(48)])
    total=models.DecimalField('Valor final',**MONEY)
    cost=models.DecimalField('Custo',**MONEY)
    status=models.CharField(max_length=20,default='confirmed',choices=[('confirmed','Confirmada'),('cancelled','Cancelada')])
    notes=models.TextField('Observações',blank=True)
    def __str__(self): return f'VEN-{str(self.id)[:8].upper()} · {self.customer}'
class SaleItem(Base):
    sale=models.ForeignKey(Sale,on_delete=models.CASCADE,related_name='items')
    variant=models.ForeignKey(Variant,on_delete=models.PROTECT)
    quantity=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price=models.DecimalField(**MONEY)
    unit_cost=models.DecimalField(**MONEY)
    class Meta: constraints=[models.CheckConstraint(condition=Q(quantity__gt=0),name='sale_qty_positive')]
class InventoryMovement(Base):
    variant=models.ForeignKey(Variant,on_delete=models.PROTECT,verbose_name='Produto/variante')
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,editable=False)
    sale=models.ForeignKey(Sale,on_delete=models.PROTECT,null=True,blank=True,editable=False)
    kind=models.CharField('Tipo',max_length=20,choices=[('in','Entrada'),('out','Saída'),('reserve','Reserva'),('release','Liberar reserva')])
    quantity=models.PositiveIntegerField('Quantidade',validators=[MinValueValidator(1)])
    reason=models.CharField('Motivo',max_length=200)
class Payment(Base):
    sale=models.ForeignKey(Sale,on_delete=models.PROTECT,related_name='payments')
    amount=models.DecimalField(**MONEY)
    method=models.CharField(max_length=20,choices=PAYMENTS)
    status=models.CharField(max_length=20,default='pending',choices=[('pending','Pendente'),('confirmed','Confirmado'),('cancelled','Cancelado')])
    due_at=models.DateField(default=timezone.localdate)
    confirmed_at=models.DateTimeField(null=True,blank=True)
class Commission(Base):
    sale=models.OneToOneField(Sale,on_delete=models.PROTECT)
    user=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='Vendedor')
    amount=models.DecimalField('Valor',**MONEY)
    status=models.CharField('Status',max_length=20,choices=[('pending','Pendente'),('approved','Aprovada'),('paid','Paga'),('cancelled','Cancelada')],default='pending')
class CommissionRule(Base):
    name=models.CharField('Nome',max_length=100)
    category=models.CharField('Categoria (vazio = todas)',max_length=100,blank=True)
    product=models.ForeignKey(Product,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Produto (opcional)')
    percent=models.DecimalField('Percentual',max_digits=5,decimal_places=2,default=0,validators=[MinValueValidator(0),MaxValueValidator(100)])
    fixed=models.DecimalField('Valor fixo por unidade',**MONEY)
    active=models.BooleanField('Ativa',default=True)
class Goal(Base):
    name=models.CharField('Meta',max_length=120)
    user=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Usuário (vazio = equipe)')
    team=models.ForeignKey(Team,on_delete=models.PROTECT,null=True,blank=True,verbose_name='Equipe')
    kind=models.CharField('Indicador',max_length=20,choices=[('revenue','Faturamento'),('sales','Vendas'),('leads','Leads'),('contacts','Contatos'),('proposals','Propostas'),('ticket','Ticket médio'),('conversion','Conversão (%)')])
    target=models.DecimalField('Objetivo',**MONEY)
    start=models.DateField('Início')
    end=models.DateField('Fim')
class Notification(Base):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications')
    title=models.CharField(max_length=200)
    link=models.CharField(max_length=250,blank=True)
    read=models.BooleanField(default=False)
    key=models.CharField(max_length=200,unique=True,null=True)
class Automation(Base):
    name=models.CharField('Nome',max_length=150)
    trigger=models.CharField('Gatilho',max_length=30,choices=[('new_lead','Novo lead'),('stage','Mudança de etapa'),('sale','Venda realizada')])
    source=models.ForeignKey(Source,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Condição: origem')
    stage=models.ForeignKey(Stage,on_delete=models.SET_NULL,null=True,blank=True,verbose_name='Condição: etapa')
    action=models.CharField('Ação',max_length=20,choices=[('task','Criar tarefa'),('assign','Distribuir para SDR')],default='task')
    delay_days=models.PositiveIntegerField('Após quantos dias',default=1)
    task_kind=models.CharField('Tipo da tarefa',max_length=30,default='return',choices=Task._meta.get_field('kind').choices)
    active=models.BooleanField('Ativa',default=True)
class AuditLog(Base):
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
    entity=models.CharField(max_length=100)
    object_id=models.CharField(max_length=100)
    action=models.CharField(max_length=100)
    before=models.JSONField(default=dict)
    after=models.JSONField(default=dict)
class Integration(Base):
    channel=models.CharField('Canal',max_length=20,choices=[('whatsapp','WhatsApp Business'),('instagram','Instagram Direct'),('ai','Inteligência artificial')],unique=True)
    account_id=models.CharField('Account / WABA ID',max_length=150,blank=True)
    phone_id=models.CharField('Phone Number ID',max_length=150,blank=True)
    enabled=models.BooleanField('Habilitada',default=False)
    def __str__(self): return self.get_channel_display()
class Company(Base):
    name=models.CharField('Nome da loja',max_length=150,default='Premium Store')
    logo=models.ImageField('Logo',upload_to='company/',blank=True)
    color=models.CharField('Cor principal',max_length=7,default='#6558f5',validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$','Informe uma cor hexadecimal, por exemplo #6558f5.')])
    business_start=models.TimeField('Início do expediente',default='09:00')
    business_end=models.TimeField('Fim do expediente',default='18:00')
    business_days=models.CharField('Dias (0=segunda, 6=domingo)',max_length=20,default='0,1,2,3,4,5')
    restrict_hours=models.BooleanField('Distribuir somente no expediente',default=True)
    round_robin_cursor=models.PositiveIntegerField(default=0,editable=False)
    followup_days=models.CharField('Follow-ups (dias separados por vírgula)',max_length=80,default='1,3,7')
    aftersale_days=models.CharField('Pós-venda (dias separados por vírgula)',max_length=80,default='1,3,7,30,180')
    sla_minutes=models.PositiveIntegerField('SLA (minutos)',default=5,validators=[MinValueValidator(1)])
class ScoringRule(Base):
    kind=models.CharField('Evento',max_length=30,choices=Activity._meta.get_field('kind').choices,unique=True)
    points=models.PositiveIntegerField('Pontos',validators=[MaxValueValidator(100)])
class SavedFilter(Base):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    module=models.CharField(max_length=50)
    name=models.CharField(max_length=100)
    params=models.JSONField(default=dict)
class ReactivationCampaign(Base):
    name=models.CharField('Campanha',max_length=150)
    months=models.PositiveIntegerField('Sem comprar há (meses)',default=6,validators=[MinValueValidator(1)])
    owner=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='Responsável')
    notes=models.TextField('Mensagem/observações',blank=True)
class LoginAttempt(models.Model):
    key=models.CharField(max_length=64,primary_key=True)
    failures=models.PositiveIntegerField(default=0)
    window_start=models.DateTimeField(default=timezone.now)
class Attachment(Base):
    product=models.ForeignKey(Product,on_delete=models.CASCADE,null=True,blank=True,related_name='photos')
    device=models.ForeignKey(UsedDevice,on_delete=models.CASCADE,null=True,blank=True,related_name='photos')
    image=models.ImageField(upload_to='attachments/')
    uploaded_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=(Q(product__isnull=False,device__isnull=True)|Q(product__isnull=True,device__isnull=False)),name='attachment_one_parent')]
class MarketingSpend(Base):
    campaign=models.ForeignKey(Campaign,on_delete=models.PROTECT,verbose_name='Campanha')
    date=models.DateField('Data do investimento',default=timezone.localdate)
    amount=models.DecimalField('Investimento realizado',**MONEY)
    notes=models.CharField('Observações',max_length=200,blank=True)
