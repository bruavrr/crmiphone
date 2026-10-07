# Validação da entrega

Validação realizada no ambiente cloud com Python 3.12, Django 5.2.18, SQLite e Chromium instalado. Aplicação funcional no ambiente de desenvolvimento; implantação externa não executada.

## Resultados

- **60 testes Django aprovados**, sem testes pulados: autenticação/limitação de tentativas, hash de senha, usuários, clientes/consentimento, CRUD de lead, round robin/expediente/capacidade, alteração de responsável, perda obrigatória, permissão de etapas SDR, transferência, scoring, tarefas, propostas multitem, follow-ups idempotentes, venda/estoque/pagamentos/comissão, falha atômica, cancelamento, reservas, troca em estoque, metas, métricas, permissões, busca/filtros/CSV/favoritos, anonimização, CSRF, notificações, automações, captura autenticada, reutilização de telefone normalizado, HMAC/idempotência de webhook, fotos protegidas, orçamento real de marketing, roles relacionais, regras de pipeline após renomear/reordenar, expiração auditada e relacionamento comercial da proposta e metas SDR após transferência.
- **93 verificações Playwright aprovadas**: módulos em desktop 1440px, tablet 820px e celular 390px; formulários mobile; menu responsivo; cadastro de cliente/lead; distribuição e qualificação; transferência; interação; proposta com dois itens, desconto e follow-ups; apresentação imprimível; venda; pagamento; comissão; tarefa concluída; meta/progresso; produto/variante; movimento de estoque; troca/margem; criação de usuário; busca; filtro favorito; relatório/CSV; Kanban persistente por drag-and-drop; bloqueios administrativos/financeiros do SDR. Nenhum erro JavaScript observado.
- Gunicorn real: `/health/`, login, dashboard, CSS servido e layout mobile verificados por navegador.
- Worker real: uma tarefa de atraso temporária gerou a notificação correspondente no ciclo do worker; tarefa/notificação de verificação removidas depois. O teste não alterou registros comerciais de demonstração.
- `manage.py check --deploy`: sem avisos na configuração de produção de validação. Isso valida configurações de segurança, não conectividade PostgreSQL ou uma implantação externa.
- `makemigrations --check --dry-run`: sem migrações faltantes.
- `scripts/setup.sh` executado e repetido com sucesso; dados existentes preservados. `run_automations` executado com sucesso.

## Demonstração final preservada

20 clientes, 30 leads, 15 oportunidades abertas, 10 produtos, 20 propostas, 10 vendas e 7 usuários. Dados históricos permitem explorar reativação; por isso o filtro “este mês” pode exibir menos vendas/leads que o total do banco. Todos os dados demonstrativos são identificados na interface.

O navegador de mutações usou `browser-test.sqlite3`, separado do banco `db.sqlite3` da demonstração final. Instalação, dependências e processos reais foram verificados. Instruções cloud `install_script` e `start_skill` foram salvas como rascunho; publicação do snapshot cabe ao usuário no produto.

## Limites objetivos da validação

PostgreSQL e imagem Docker possuem configuração/migrações preparadas, mas não foram executados nesta infraestrutura. Testes de concorrência PostgreSQL, teste de carga, backup/restauração e observabilidade da hospedagem devem ser executados durante implantação. Nenhum acesso real Meta ou provedor IA foi configurado; transporte/webhooks foram verificados com dados de teste, sem afirmar envio externo. Exportação é CSV compatível com Excel; PDF é gerado pela impressão do navegador. Pagamentos/comissões são registros, sem cobrança ou transferência financeira automática. A política LGPD deve ser adaptada à operação da loja.

Consulte README.md para comandos, acesso demonstrativo, permissões, integrações e implantação.
