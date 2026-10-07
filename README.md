# Premium CRM — lojas de iPhone e smartphones

Aplicação funcional Django 5.2 LTS com banco relacional, autenticação por sessão, cinco perfis, controles no servidor e interface responsiva. Todas as métricas, tabelas, filtros, propostas, tarefas e cards são consultados do banco. A demonstração é explícita e separada de produção.

## Executar no ambiente de desenvolvimento

### Abrir no VS Code no seu computador

Baixe pelo GitHub em **Code → Download ZIP**, extraia e abra a pasta que contém `manage.py` no VS Code. Instale Python 3.12 ou superior e abra **Terminal → Novo Terminal**.

- Windows: `py iniciar.py`
- macOS/Linux: `python3 iniciar.py`

O iniciador instala as dependências, cria a demonstração em `demo.sqlite3` (separada do banco padrão), prepara os arquivos estáticos e inicia o CRM e o worker de automações. No navegador do seu computador, abra `http://127.0.0.1:8000`. Login: `admin` / `Demo@Premium2026!`. Mantenha o terminal aberto; **Ctrl+C** encerra os processos. A primeira execução requer internet para instalar as dependências. Use esse iniciador somente para demonstração local, nunca em produção.

O banco e os arquivos enviados não são publicados no GitHub. A demonstração é gerada localmente na primeira execução e preservada nas seguintes.

### Ambiente na nuvem

```bash
cd /workspace/crmiphone
bash scripts/setup.sh
.venv/bin/python manage.py runserver 0.0.0.0:8000
# Em outro processo: distribuição pendente, SLA, expiração e notificações.
.venv/bin/python manage.py automation_worker
```

Use o checkout existente. Cada tarefa cloud já é isolada; não crie worktrees para iniciar o sistema. Processos precisam reiniciar depois de restaurar o ambiente. Banco, arquivos enviados e dependências permanecem no filesystem preparado; não dependa de um PID de uma sessão anterior.

### Demonstração

O banco preparado nesta tarefa contém 20 clientes, 30 leads, 10 produtos com variantes, 20 propostas, 10 vendas, metas, tarefas, interações e sete usuários. Os registros fictícios possuem `is_demo`; o workspace mostra um aviso persistente. Nenhuma mensagem externa foi inventada.

**Acesso exclusivamente demonstrativo:** usuário `admin`, senha `Demo@Premium2026!`.
Outros perfis: `gestor`, `bruna`, `mariaclara`, `joao`, `rafaela`, `posvenda`, com a mesma senha demonstrativa. Não use esses usuários/senhas em produção.

Para criar a demonstração em um banco **vazio** separado:

```bash
# A variável recebe uma senha de demonstração definida por você.
.venv/bin/python manage.py seed_demo --password "$CRM_DEMO_PASSWORD"
```

O comando não sobrescreve usuários nem dados comerciais existentes e é idempotente depois de criar a demo. `setup.sh` não cria contas de demonstração automaticamente.

## Fluxo diário

1. Cadastre um cliente e um lead, ou capture via API/formulário/Meta conectado.
2. O round robin atribui SDR ativo e disponível, respeitando expediente e capacidade. Leads sem SDR elegível ficam pendentes; o worker tenta novamente.
3. Abra o lead, registre o contato e qualifique. Abrir WhatsApp não equivale a confirmar envio. Interações registradas atualizam primeiro contato, SLA, pontuação e linha do tempo.
4. Transfira o lead qualificado para um vendedor. O histórico registra responsáveis anteriores e novos.
5. Gere proposta com um ou vários produtos, desconto, entrada, troca, parcelas e validade. A apresentação pode ser impressa/salva em PDF pelo navegador. Preparar envio agenda follow-ups; entrega externa não é afirmada.
6. Registre a venda: valida itens e saldo, debita estoque disponível, registra custo histórico, pagamentos pendentes, comissão e tarefas de pós-venda em uma transação.
7. Confirme pagamentos efetivamente recebidos. A gestão aprova/paga comissões; pagar comissão exige pagamentos confirmados.
8. Pós-venda acompanha tarefas; reativação segmenta histórico de compras. Campanhas criam tarefas apenas para clientes com consentimento. Upgrade é uma heurística explícita de tempo desde a última compra, não IA.

## Módulos e regras implementados

- Clientes, leads, origens, campanhas, UTMs, usuários, equipes, produtos/variantes, trocas, tarefas, metas e automações: formulários persistidos e validação no servidor.
- Ficha do cliente com dados, leads, interações, propostas, compras, tarefas e histórico. Anonimização remove dados pessoais e conteúdos vinculados, preservando referências comerciais/fiscais e autoria da auditoria.
- Pipeline com drag-and-drop no desktop e mudança de etapa no formulário no celular. Etapas têm função semântica, permissão de SDR e qualificação configuráveis; renomear/reordenar não altera essas regras. Registram data/usuário; perda exige motivo; etapa de venda exige venda existente.
- Distribuição round robin com cursor persistido e histórico. Disponibilidade/limites por usuário, horários/dias e SLA configuráveis na empresa.
- Tarefas com prioridade, data/hora, dono, cliente e lead; atrasos e conclusão. Intervalos de follow-up/pós-venda são configuráveis; criação automática é idempotente.
- Produtos futuros são dados do catálogo, sem enumeração no código. Variantes possuem capacidade, cor, condição, preço, promoção, custo, IMEI/serial. IMEI/serial não vazios são únicos; aparelhos identificados não permitem quantidade maior que um.
- Estoque com disponível, reservado, vendido, mínimo, alertas e movimentos auditados. Quantidades mudam por movimento ou venda, não por edição arbitrária. Reservas manuais reduzem disponibilidade e devem ser liberadas antes de venda.
- Trocas com checklist, fotos protegidas, bateria, custo total e margem estimada. Ao efetivar uma venda com troca, o aparelho recebido vira variante usada e entra no estoque.
- Propostas multitem, impressão profissional, validade/status, envio preparado, negociação, recusa e conversão. Status de visualização é registro manual confirmado, não rastreamento simulado de leitura.
- Venda, pagamentos, comissão percentual/fixa por usuário, produto ou categoria; regra de produto tem prioridade. Itens guardam preços/custos históricos. Venda cancelada repõe estoque; comissão paga bloqueia cancelamento até tratar o estorno financeiro.
- Metas individuais/equipe para leads, contatos, propostas, vendas, faturamento, ticket e conversão, com progresso calculado.
- Dashboard/relatórios por período, origens, campanhas, SDR, vendedores, produtos, perdas, receita, margem, ticket e conversão. CAC usa novos compradores e despesas de marketing por data; ROI = (receita − investimento) / investimento; LTV é receita histórica média por cliente. Sem denominador/investimento, o indicador informa dados insuficientes.
- Busca por nome/telefone/WhatsApp/Instagram/e-mail/IMEI/serial/produto/número de proposta/venda; filtros, favoritos, paginação e CSV UTF-8 compatível com Excel, protegido contra injeção de fórmulas. Não há gerador nativo XLSX.
- Inbox com conversas reais, estados, vínculo cliente/lead e transporte oficial Meta. Sem credenciais, exibe integração desconectada e bloqueia envio.
- Notificações de leads, mensagens, estoque, SLA, tarefas e metas; auditoria com antes/depois, autor e data. Campos de senha nunca entram na auditoria.

## Permissões

| Perfil | Acesso |
|---|---|
| Administrador | Todos os módulos e configurações, usuários e integrações |
| Gestor | Operação comercial, equipe, distribuição, relatórios, metas; sem usuários/credenciais |
| SDR | Próprios leads/clientes relacionados, atividades, tarefas, qualificação e transferência |
| Vendedor | Próprios leads, propostas, vendas e comissões; consulta catálogo/estoque |
| Pós-venda | Clientes com vendas, interações, tarefas, inbox e campanhas de relacionamento |

Consultas, detalhes, mutações e exportações verificam perfil e escopo. Não há cadastro público de usuários. Senhas usam o hash PBKDF2 do Django; há validação de senhas, CSRF, cookies de sessão, proteção de rotas, limitação de tentativas de login e CSP. O sistema atende uma única empresa por instalação, com múltiplas equipes; não é um SaaS multiempresa.

## APIs e integrações

`POST /api/leads/` exige `X-API-Key` igual a `LEAD_API_KEY`. Exemplo de corpo:

```json
{"name":"Nome do cliente","phone":"11999999999","email":"cliente@example.com","source":"Formulário","consent":true,"utm_source":"instagram","utm_campaign":"upgrade"}
```

Telefone normalizado permite reutilizar o cliente existente; cada nova captura cria um lead. Resposta 201 contém UUID. Sem chave configurada, a API rejeita o pedido. Para formulários públicos, mantenha a chave no backend da landing page, nunca no JavaScript público.

`GET/POST /webhooks/meta/` implementa desafio e validação HMAC SHA-256. Eventos recebidos são idempotentes por ID de mensagem. A conta receptora deve corresponder à integração habilitada. Somente mensagens reais de texto são armazenadas; anexos externos/templates/broadcasts exigem evolução específica da integração.

Configure IDs na tela Integrações e **segredos no servidor**, nunca no código:

- `META_ACCESS_TOKEN`: token oficial válido, com permissões e contas aprovadas;
- `META_APP_SECRET`: verificação da assinatura dos webhooks;
- `META_VERIFY_TOKEN`: desafio do endpoint público HTTPS;
- WhatsApp Business Account ID / Phone Number ID;
- Instagram Account ID.

Envio usa endpoints oficiais Meta v23.0. WhatsApp exige janela de atendimento/permissões aplicáveis; Instagram exige conta profissional/configuração Meta válida. O aplicativo só registra envio depois de obter um ID aceito pela API; status de entrega depende do webhook. Configure egress `graph.facebook.com` e `graph.instagram.com` quando ativar as integrações; nenhum acesso a esses serviços foi declarado como validado nesta tarefa.

`crm/ai.py` define o contrato de um provedor de IA; nenhum provedor/resposta artificial está ativado. Use contexto minimizado e avaliação de privacidade antes de implementar um provedor. Integrações com anúncios podem capturar leads pela API com UTMs; não há sincronização automática de investimento com Meta Ads.

## Testes

```bash
.venv/bin/python manage.py test
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py run_automations
```

O teste de navegador exige `requirements-dev.txt` e Chromium. Use **um banco separado**:

```bash
.venv/bin/pip install -r requirements-dev.txt
SQLITE_PATH=/tmp/crm-browser.sqlite3 .venv/bin/python manage.py migrate
SQLITE_PATH=/tmp/crm-browser.sqlite3 .venv/bin/python manage.py seed_demo --password "$CRM_DEMO_PASSWORD"
SQLITE_PATH=/tmp/crm-browser.sqlite3 .venv/bin/python manage.py runserver 127.0.0.1:8001 --noreload
# Outro processo, com CRM_DEMO_PASSWORD definido:
.venv/bin/python scripts/browser_smoke.py
```

O script usa o Chromium instalado em `/usr/bin/chromium` (override `CHROMIUM_PATH`), valida desktop/tablet/mobile e executa CRUDs e fluxo lead → proposta → venda → pagamento → comissão. Relatórios e screenshots vão para `/tmp/crm-evidence`. Ele cria registros identificados E2E no banco de teste e não deve rodar em produção.

## Implantação com PostgreSQL

Arquivos de referência: `Dockerfile`, `compose.yaml`, `.env.example`, `deploy/nginx.conf.example`. Não foi publicada uma instância externa nesta tarefa. Os testes locais usam SQLite; validação de Docker/PostgreSQL, backups e restauração na infraestrutura real devem fazer parte da implantação.

1. Configure `.env` a partir do exemplo, sem versionar segredos. Use `DEBUG=false`, SECRET_KEY aleatória, domínio real em ALLOWED_HOSTS e DATABASE_URL PostgreSQL. Sem chave/DB de produção, a aplicação recusa inicialização.
2. Compile a imagem, inicie somente o banco e aplique migrações/configurações:

```bash
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate --noinput
docker compose run --rm web python manage.py init_crm
docker compose run --rm web python manage.py createsuperuser --role admin
docker compose up -d web automations
```

3. Configure reverse proxy HTTPS, certificado e cabeçalhos confiáveis. O exemplo Nginx substitui `X-Forwarded-Proto`; `TRUST_PROXY=true` é adequado somente atrás desse proxy. O Compose mantém PostgreSQL sem porta publicada e web ligada ao loopback. TLS de banco só é desativado na rede interna isolada do Compose; para banco remoto, use SSL verificado conforme a infraestrutura.
4. Faça smoke test autenticado, teste de backup/restauração e verificação `manage.py check --deploy` com variáveis reais. Estabeleça monitoramento do worker e rotina de backup do PostgreSQL e volume `media`. Endpoint `/health/` verifica conectividade do banco, sem dados comerciais.
5. Defina contatos/retenção/bases legais da loja no texto de privacidade e procedimento LGPD. Anonimização no banco ativo não apaga backups históricos; aplique a política de retenção aos backups.
6. Não copie o banco demo para operação real. Integrações, pagamentos e comissões são registros comerciais; o CRM não processa cartão, PIX, NF-e nem estornos externos. Não contém antifraude, conciliação bancária automática ou um provedor fiscal.

Arquitetura detalhada em [ARCHITECTURE.md](ARCHITECTURE.md). Dados enviados não são servidos publicamente por `/media/`: fotos usam endpoints autenticados com o mesmo escopo do registro.
