# CRM Premium — decisões de arquitetura

Monólito modular Django 5.2 LTS: ORM relacional, formulários com validação no servidor, sessão autenticada, CSRF, templates responsivos e JavaScript progressivo. PostgreSQL em produção; SQLite somente para desenvolvimento. Valores financeiros usam Decimal. IDs UUID nas entidades comerciais, timestamps e relacionamentos com proteção de exclusão.

## Domínios e relacionamentos
Usuários → funções/equipes; clientes → leads → atividades/histórico/tarefas/conversas/propostas/vendas. Produto → variantes → estoque e movimentos. Venda → itens/pagamentos/comissões; aparelhos de troca pertencem a clientes e podem compor propostas/vendas. Origens → campanhas → leads; automações → tarefas; metas → usuários/equipes; auditoria registra operações autenticadas. Histórico comercial mantém referências e evita duplicação de dados pessoais.

## Acesso
Administrador configura usuários/integrações e todas as operações. Gestor acessa gestão comercial, sem configuração de credenciais. SDR acessa próprios leads e clientes relacionados, qualificação, atividades e tarefas; não recebe relatórios financeiros. Vendedor acessa próprios leads, clientes, propostas e vendas. Pós-venda acessa clientes com vendas, interações e tarefas. Todas as consultas e mutações validam escopo no servidor; esconder menu não constitui autorização.

## Regras
Distribuição round robin transacional com cursor persistente, usuários ativos/disponíveis, horário comercial e limite de atendimento. Etapas mantêm autor/data; perda exige motivo. Proposta enviada agenda follow-ups configuráveis. Venda efetiva debita estoque, calcula comissão e agenda pós-venda atomicamente. Cancelamento repõe estoque e cancela pagamentos/comissões. Agendador idempotente executado por cron, sem depender de processo web. Mensagens externas só são registradas como enviadas depois de sucesso confirmado pela API; abertura de WhatsApp é apenas abertura, sem confirmação de envio.

## Interface e endpoints
Páginas autenticadas em /dashboard/, /leads/, /customers/, /pipeline/, /inbox/, /tasks/, /products/, /inventory/, /trades/, /proposals/, /sales/, /commissions/, /goals/, /reports/, /settings/. CRUD usa formulários POST com CSRF e PRG. Pipeline usa endpoint POST /leads/<id>/stage/. Busca global, filtros GET, favoritos persistidos. CSV UTF-8 protegido contra fórmulas, propostas imprimíveis. Endpoints públicos /api/leads/ usam chave secreta; /webhooks/meta/ verifica assinatura HMAC e desafio configurado, sem simular integração.

## Produção
Configuração exclusivamente por variáveis de ambiente. DEBUG desativado exige SECRET_KEY e ALLOWED_HOSTS. HTTPS, cookies seguros, backups, cron, armazenamento de mídia e reverse proxy são responsabilidade da implantação. Segredos nunca em templates ou auditoria. Demo por comando explícito, marcada na interface, não executada em produção automaticamente. Métricas vêm do banco; CAC/ROI dependem de investimento e são apresentados como dados insuficientes quando ausentes. IA é ponto de extensão desativado sem provedor.
