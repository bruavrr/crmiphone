from .permissions import allowed
from . import models as m
NAV=[('dashboard','Visão geral','◫','PRINCIPAL'),('leads','Leads','◎',''),('inbox','Inbox','▤',''),('customers','Clientes','♙',''),('pipeline','Pipeline','▥',''),('proposals','Propostas','▧','COMERCIAL'),('sales','Vendas','↗',''),('products','Produtos','◇',''),('inventory','Estoque','▦',''),('trades','Trocas','⇄',''),('tasks','Tarefas','✓','RELACIONAMENTO'),('aftercare','Pós-venda','♡',''),('reactivation','Reativação','⟳',''),('goals','Metas','◉','GESTÃO'),('commissions','Comissões','＄',''),('reports','Relatórios','▤',''),('settings','Configurações','⚙','')]
ICONS={
'dashboard':'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
'leads':'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
'inbox':'M21 15V4H3v11 M3 15h5l2 3h4l2-3h5v6H3z',
'customers':'M20 21v-2a7 7 0 0 0-14 0v2 M17 7a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
'pipeline':'M3 3h18v18H3z M9 3v18 M15 3v18 M5 7h2 M11 10h2 M17 14h2',
'proposals':'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h5',
'sales':'M3 17l6-6 4 4 8-11 M15 4h6v6',
'products':'M12 3l8 4v10l-8 4-8-4V7z M4 7l8 5 8-5 M12 12v9',
'inventory':'M3 3h18v18H3z M3 9h18 M9 9v12 M15 9v12',
'trades':'M3 7h18 M17 3l4 4-4 4 M21 17H3 M7 13l-4 4 4 4',
'tasks':'M9 11l3 3L22 4 M21 12v8H3V3h12',
'aftercare':'M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8',
'reactivation':'M21 3v6h-6 M3 21v-6h6 M3.5 9A9 9 0 0 1 18 5l3 4 M3 15l3 4a9 9 0 0 0 14.5-4',
'goals':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0 M13 12h-2',
'commissions':'M12 2v20 M17 5H9a3 3 0 0 0 0 6h6a3 3 0 0 1 0 6H6',
'reports':'M3 3v18h18 M7 16v-3 M12 16V8 M17 16V5',
'settings':'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8 M10 2h4l1 3 3 1 3 1v4l-3 1-1 3-1 3h-4l-1-3-3-1-3-1v-4l3-1 1-3z'}
def navigation(request):
    if not request.user.is_authenticated: return {}
    company=m.Company.objects.first()
    return {'navigation':[{'module':module,'name':name,'icon':icon,'path':ICONS.get(module,''),'section':section,'url':f'/{module}/'} for module,name,icon,section in NAV if allowed(request.user,module)],'store':company,'demo_mode':request.user.is_demo or bool(company and company.is_demo),'notification_count':m.Notification.objects.filter(user=request.user,read=False).count(),'can_manage':request.user.role_code in {'admin','manager'},'can_leads':allowed(request.user,'leads'),'can_sell':request.user.role_code in {'admin','manager','seller'},'can_admin':request.user.role_code=='admin'}
