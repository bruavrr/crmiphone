from django.db import migrations

def initialize(apps,schema_editor):
    Stage=apps.get_model('crm','Stage'); Lead=apps.get_model('crm','Lead'); alias=schema_editor.connection.alias
    stages=['Novo lead','Primeiro contato','Em atendimento','Qualificado','Produto de interesse','Proposta enviada','Negociação','Aguardando pagamento','Venda realizada','Pós-venda','Perdido']
    for i,name in enumerate(stages):
        stage=Stage.objects.using(alias).filter(name=name).order_by('position').first()
        if stage:
            stage.behavior={0:'new',5:'proposal',6:'negotiation',7:'payment'}.get(i,'standard')
            stage.allows_sdr=i<=4 or i==10; stage.qualifies_lead=3<=i<=9
            stage.save(update_fields=['behavior','allows_sdr','qualifies_lead'],using=alias)
    for lead in Lead.objects.using(alias).filter(stage__qualifies_lead=True,qualified_at__isnull=True).iterator():
        lead.qualified_at=lead.stage_changed_at; lead.save(update_fields=['qualified_at'],using=alias)
class Migration(migrations.Migration):
    dependencies=[('crm','0009_lead_qualified_at_stage_allows_sdr_stage_behavior_and_more')]
    operations=[migrations.RunPython(initialize,migrations.RunPython.noop)]
