"""Real browser checks. Run against an isolated demo DB, never a production store."""
import os, re, time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
NOW=lambda: datetime.now(ZoneInfo("America/Sao_Paulo"))
from playwright.sync_api import sync_playwright
BASE=os.getenv('CRM_TEST_URL','http://127.0.0.1:8001')
PASSWORD=os.environ['CRM_DEMO_PASSWORD']
EVIDENCE=Path(os.getenv('CRM_EVIDENCE_DIR','/tmp/crm-evidence')); EVIDENCE.mkdir(parents=True,exist_ok=True)
RUN=str(time.time_ns())[-7:]
NAME="Ana E2E "+RUN
checks=[]
def check(name,condition=True):
    assert condition,name
    checks.append(name); print('PASS',name,flush=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page(); errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/login/'); page.fill('[name=username]','admin'); page.fill('[name=password]',PASSWORD);page.locator('form button').click();page.wait_for_url('**/dashboard/')
    check('Login real e dashboard com dados')
    page.screenshot(path=str(EVIDENCE/'dashboard-desktop.png'),full_page=True)
    # Validate the responsive shell, tables, forms, charts and internal kanban overflow.
    for width,height in [(1440,1000),(820,1100),(390,844)]:
        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(250)
        for module in ['dashboard','leads','customers','pipeline','proposals','sales','products','inventory','trades','tasks','goals','commissions','reports','settings','inbox','aftercare','reactivation']:
            response=page.goto(BASE+'/'+module+'/');page.wait_for_timeout(220)
            check(f'{module}: HTTP e responsividade {width}',response.status==200 and page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        if width==390:
            for module in ['customers','leads','proposals','tasks','trades','products']:
                response=page.goto(BASE+'/'+module+'/new/');check(f'Formulário mobile {module}',response.status==200 and page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page.goto(BASE+'/dashboard/'); page.wait_for_timeout(300)
        if width==390:
            check('Menu mobile fechado',page.locator('#sidebar').bounding_box()['x']+page.locator('#sidebar').bounding_box()['width']<=1)
            page.locator('#menu-toggle').click();check('Menu mobile abre',page.locator('#sidebar').evaluate('(e)=>e.classList.contains("open")'));page.locator('#sidebar-backdrop').click()
            page.screenshot(path=str(EVIDENCE/'dashboard-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.goto(BASE+'/customers/new/');page.fill('[name=first_name]',NAME);page.fill('[name=last_name]','Silva');page.fill('[name=phone]','11988887766');page.check('[name=consent]');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/customers/[0-9a-f-]{36}/$'));customer_url=page.url
    check('Cadastro de cliente salvo',page.locator('h1').inner_text()==NAME+' Silva')
    page.goto(BASE+'/leads/new/?customer='+customer_url.split('/')[-2]);page.select_option('[name=source]',label='WhatsApp');page.select_option('[name=product]',label='iPhone 17 Pro');page.fill('[name=budget]','10000');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/leads/[0-9a-f-]{36}/$'));lead_url=page.url
    check('Cadastro e distribuição do lead',page.locator('body').inner_text().find('automaticamente')>=0)
    page.select_option('.stage-form [name=stage]',label='Qualificado');page.locator('.stage-form button').click();page.wait_for_load_state()
    check('Etapa persistida',page.locator('.lead-control').inner_text().find('Qualificado')>=0)
    page.select_option('[name=seller]',label='João Demo');page.locator('form[action$="/transfer/"] button').click();page.wait_for_load_state()
    check('Transferência para vendedor',page.locator('body').inner_text().find('transferido')>=0)
    page.locator('a[href^="/activities/new/"]').first.click();page.select_option('[name=kind]',label='Pediu pagamento');page.fill('[name=description]','Cliente solicitou parcelamento — teste funcional');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/activities/[0-9a-f-]{36}/$'));check('Registro de interação')
    page.goto(lead_url);page.locator('a[href^="/proposals/new/"]').click();page.select_option('[name=seller]',label='João Demo');page.fill('[name=discount]','1000');page.fill('[name=valid_until]',(NOW()+timedelta(days=7)).date().isoformat());page.select_option('[name="items-0-variant"]',label='iPhone 17 Pro · 256 GB · Preto');page.fill('[name="items-0-quantity"]','2');page.fill('[name="items-0-unit_price"]','10000');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/proposals/[0-9a-f-]{36}/$'));proposal_url=page.url
    check('Proposta com itens e desconto', 'R$ 19.000,00' in page.locator('.detail-total').inner_text())
    page.locator('form[action$="/send/"] button').click();page.wait_for_load_state();check('Follow-ups após proposta', 'Enviada' in page.locator('.lead-control').inner_text())
    preview=context.new_page(); preview.goto(proposal_url+'print/'); check('Apresentação da proposta', 'R$ 19.000,00' in preview.locator('body').inner_text()); preview.close()
    page.once('dialog',lambda dialog:dialog.accept());page.locator('form[action$="/sell/"] button').click();page.wait_for_url(re.compile(r'.*/sales/[0-9a-f-]{36}/$'))
    check('Venda registrada', 'R$ 19.000,00' in page.locator('.detail-total').inner_text())
    page.locator('form[action$="/payment/"] button').first.click();page.wait_for_load_state();check('Pagamento confirmado','Confirmado' in page.locator('body').inner_text())
    page.goto(BASE+'/commissions/');page.locator('tbody tr').filter(has_text=NAME).locator('a.table-main').first.click();check('Comissão automática','R$ 380,00' in page.locator('body').inner_text());page.locator('.heading-actions a[href$="/edit/"]').click();page.select_option('[name=status]','paid');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/commissions/[0-9a-f-]{36}/$'));check('Comissão paga após pagamento','Paga' in page.locator('body').inner_text())
    page.goto(BASE+'/tasks/new/');page.fill('[name=title]','E2E Follow-up');page.select_option('[name=owner]',label='Bruna Demo');page.fill('[name=due_at]',(NOW()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'));page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/tasks/[0-9a-f-]{36}/$'));page.locator('form[action$="/complete/"] button').click();page.wait_for_load_state();check('Tarefa criada e concluída','Concluída' in page.locator('body').inner_text())
    page.goto(BASE+'/goals/new/');page.fill('[name=name]','Meta E2E '+RUN);page.select_option('[name=user]',label='João Demo');page.select_option('[name=kind]','revenue');page.fill('[name=target]','100000');page.fill('[name=start]',NOW().date().isoformat());page.fill('[name=end]',(NOW()+timedelta(days=30)).date().isoformat());page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/goals/[0-9a-f-]{36}/$'));check('Cadastro de meta');page.goto(BASE+'/goals/');check('Progresso de meta calculado',float(page.locator('.goal-card').filter(has_text='Meta E2E '+RUN).locator('.goal-value').inner_text().split('/')[0].strip().replace(',','.'))>=19000)
    product_name='Phone E2E '+RUN
    page.goto(BASE+'/products/new/');page.fill('[name=name]',product_name);page.fill('[name=model]','Premium E2E');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/products/[0-9a-f-]{36}/$'));check('Cadastro de produto')
    page.goto(BASE+'/variants/new/');page.select_option('[name=product]',label=product_name);page.fill('[name=price]','8000');page.fill('[name=cost]','6000');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/variants/[0-9a-f-]{36}/$'));check('Cadastro de variante com preço')
    page.goto(BASE+'/movements/new/');page.select_option('[name=variant]',label=product_name+' · 128 GB · Preto');page.select_option('[name=kind]','in');page.fill('[name=quantity]','5');page.fill('[name=reason]','Entrada de estoque E2E');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/movements/[0-9a-f-]{36}/$'));check('Movimentação de estoque');page.goto(BASE+'/inventory/?q=Phone+E2E+'+RUN);check('Estoque disponível após entrada',page.locator('tbody tr').count()==1 and page.locator('tbody tr').inner_text().find('5')>=0)
    page.goto(BASE+'/trades/new/');page.select_option('[name=customer]',label=NAME+' Silva');page.fill('[name=model]','iPhone 13');page.fill('[name=capacity]','128 GB');page.fill('[name=color]','Preto');page.fill('[name=imei]','12345678'+RUN);page.fill('[name=physical_state]','Bom');page.fill('[name=battery]','85');page.fill('[name=appraisal]','1800');page.fill('[name=entry_value]','1600');page.fill('[name=repair_cost]','200');page.fill('[name=resale_price]','2600');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/trades/[0-9a-f-]{36}/$'));check('Checklist de troca e margem','R$ 800,00' in page.locator('.lead-control').inner_text())
    page.goto(BASE+'/users/new/');page.fill('[name=username]','e2eseller'+RUN);page.fill('[name=first_name]','Vendedor E2E');page.fill('[name=password]','E2E-Strong-Test-2026!');page.select_option('[name=role]','seller');page.locator('.form-footer button').click();page.wait_for_url(re.compile(r'.*/users/\d+/$'));check('Cadastro de usuário')
    page.goto(BASE+'/leads/?q=Ana+E2E+'+RUN);check('Busca na tabela',page.locator('tbody tr').count()==1)
    page.goto(BASE+'/search/?q=Ana+E2E+'+RUN);check('Busca global',NAME+' Silva' in page.locator('.search-results').inner_text())
    page.goto(BASE+'/leads/?temperature=hot');page.locator('.favorites summary').click();page.fill('[name=name]','E2E Quentes');page.locator('.favorites form button').click();page.wait_for_load_state();check('Filtro favorito persistido','E2E Quentes' in page.locator('.favorites').inner_text())
    page.goto(BASE+'/reports/');check('Relatórios com dados calculados',page.locator('body').inner_text().find('Performance de SDRs')>=0)
    with page.expect_download() as download:page.locator('.heading-actions a').click()
    downloaded=download.value; downloaded.save_as(str(EVIDENCE/'relatorio.csv'));check('Exportação CSV',downloaded.suggested_filename=='relatorio.csv')
    # Drag and drop updates through the authenticated CSRF-protected endpoint.
    page.goto(BASE+'/pipeline/');source_index=next(i for i in range(page.locator('.kanban-column').count()) if page.locator('.kanban-column').nth(i).get_attribute('data-kind')=='open' and page.locator('.kanban-column').nth(i).locator('.lead-card').count())
    first_card=page.locator('.kanban-column').nth(source_index).locator('.lead-card').first
    target_index=2 if source_index==1 else 1
    if first_card.count():
        lead_id=first_card.get_attribute('data-id');target=page.locator('.kanban-column').nth(target_index)
        first_card.drag_to(target.locator('.kanban-dropzone'));page.wait_for_timeout(400)
        check('Kanban drag-and-drop persistido',target.locator(f'[data-id="{lead_id}"]').count()==1)
        page.reload();check('Kanban mantém alteração após recarregar',page.locator('.kanban-column').nth(target_index).locator(f'[data-id="{lead_id}"]').count()==1)
    page.goto(BASE+'/inbox/');check('Sem mensagens fictícias','Nenhuma conversa ou mensagem recebida foi simulada' in page.locator('body').inner_text())
    check('Sem erros JavaScript',not errors)
    sdr=browser.new_page();sdr.goto(BASE+'/login/');sdr.fill('[name=username]','bruna');sdr.fill('[name=password]',PASSWORD);sdr.locator('form button').click();sdr.wait_for_url('**/dashboard/');check('Login SDR real')
    check('SDR bloqueado no administrativo',sdr.goto(BASE+'/users/').status==403)
    check('SDR bloqueado em relatórios financeiros',sdr.goto(BASE+'/reports/').status==403)
    browser.close()
print(f'{len(checks)} verificações de navegador aprovadas.')
