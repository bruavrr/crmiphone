import re
from django.db import migrations

def normalize(apps,schema_editor):
    Customer=apps.get_model('crm','Customer')
    for customer in Customer.objects.using(schema_editor.connection.alias).all().iterator():
        phone=re.sub(r'\D','',customer.whatsapp or customer.phone or '')
        customer.contact_key='55'+phone if len(phone) in {10,11} else phone
        customer.save(update_fields=['contact_key'],using=schema_editor.connection.alias)
class Migration(migrations.Migration):
    dependencies=[('crm','0005_customer_contact_key_alter_customer_phone')]
    operations=[migrations.RunPython(normalize,migrations.RunPython.noop)]
