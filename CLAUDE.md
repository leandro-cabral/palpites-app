# Copa Elevação Sabichão - Documentação do Projeto

## Visão Geral
Aplicativo web interativo de palpites de futebol focado em risco e recompensa, construído com Python e Streamlit. Os usuários apostam em resultados de partidas (focando no Brasileirão) gerenciando uma banca virtual de "Elevação Coins" (EC).

O diferencial do sistema é a mecânica de "Surrealidade", que incentiva palpites ousados e multiplica os pontos e lucros.

---

## Stack Tecnológica
- **Linguagem Principal:** Python 3.x
- **Framework Web (Frontend/UI):** Streamlit
- **Banco de Dados:** Supabase (PostgreSQL)
- **Conector do Banco:** `psycopg2-binary` via `ConnectionWrapper` em `database.py`
- **Hospedagem:** Streamlit Community Cloud (conectado ao GitHub)

---

## Regras de Negócio

### 1. Sistema de Pontuação (Água da Vida)
- **+4.5 pts:** Acertou o placar exato
- **+3.0 pts:** Acertou que seria empate, mas errou o placar
- **+1.5 pts:** Acertou o time vencedor, mas errou o placar
- **-1.0 pt:** Errou totalmente o resultado

### 2. Mecânica de Surrealidade (O Chamado do Verme)
Um palpite ativa a Surrealidade se atender **pelo menos uma** destas condições:
- `abs(palpite_casa - palpite_fora) >= 3` (diferença de 3+ gols)
- `(palpite_casa + palpite_fora) >= 4` (total de 4+ gols)

**Efeitos:**
- Acerto de qualquer tipo → **Pontos × 2**
- Erro total → **Punição dobrada (-2.0 pts)**

### 3. Economia (Elevação Coins - EC)
Jogadores iniciam com `10.0 EC` (coluna `saldo_ec` na tabela `usuarios`).
- **Lucro base:** `Valor Apostado × Odd - Valor Apostado`
- **Buff placar exato:** Odd recebe bônus de 1.5× antes do cálculo
- **Buff Surrealidade (acerto):** Lucro líquido em EC × 2
- **Erro:** Perde apenas o valor apostado

### 4. Ranking Lisan al Gaib
- **Score:** `Total de Pontos × Banca Disponível`
- Banca Disponível = Saldo EC − EC em apostas ativas
- **Desempate:** 1º Maior Score → 2º Mais Pontos → 3º Mais Placares Exatos

---

## Estrutura do Banco de Dados (Supabase/PostgreSQL)

### Tabela: `usuarios`
| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL PK | Auto-incremento |
| `nome` | TEXT UNIQUE NOT NULL | Nome de login |
| `saldo_ec` | REAL DEFAULT 10.0 | Banca do jogador |
| `avatar_style` | TEXT DEFAULT '⚽' | Emoji do avatar |
| `senha_hash` | TEXT | SHA-256 da senha |
| `discord_id` | TEXT UNIQUE | ID do usuário no Discord (vinculado via `/vincular`) |
| `criado_em` | TIMESTAMPTZ DEFAULT NOW() | Data de cadastro |

### Tabela: `palpites`
| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL PK | Auto-incremento |
| `usuario` | TEXT NOT NULL | Nome do jogador |
| `jogo_id` | TEXT NOT NULL | ID do jogo (UNIQUE com usuario) |
| `jogo` | TEXT NOT NULL | Label do jogo (ex: "Flamengo x Vasco") |
| `liga` | TEXT | Nome da liga |
| `palpite_casa` | INTEGER NOT NULL | Placar apostado time da casa |
| `palpite_fora` | INTEGER NOT NULL | Placar apostado time visitante |
| `gols_casa_real` | INTEGER | Resultado real casa |
| `gols_fora_real` | INTEGER | Resultado real fora |
| `pontos` | REAL | Pontuação calculada (pode ser 4.5, 9.0 etc.) |
| `moeda_apostada` | REAL DEFAULT 0 | EC apostado |
| `moedas_ganhas` | REAL | EC ganho/perdido |
| `odds_casa` | REAL | Odd do time da casa |
| `odds_empate` | REAL | Odd do empate |
| `odds_fora` | REAL | Odd do time visitante |
| `odd_apostada` | REAL | Odd do resultado apostado |
| `criado_em` | TIMESTAMPTZ DEFAULT NOW() | Data do palpite |

> A combinação `(usuario, jogo_id)` é UNIQUE — cada jogador tem um palpite por jogo.

---

## Diretrizes para Desenvolvimento

### Banco de dados
- **Nunca use SQLite.** O projeto usa PostgreSQL via Supabase. Não use o módulo nativo `sqlite3`.
- **Placeholders SQL:** O `ConnectionWrapper` em `database.py` converte automaticamente `?` → `%s`. Nas queries Python, use `?` — o wrapper trata a conversão. Nunca use f-strings para interpolar variáveis em SQL (risco de SQL Injection).
- **Conexões:** Sempre feche a conexão (`conn.close()`) antes de chamar `st.rerun()` para evitar connection leaks.

### Frontend
- Priorize injeção de HTML/CSS com temática "Dark Mode / Duna" usando `st.markdown(unsafe_allow_html=True)` ou `st.components.v1.html()`.
- O CSS responsivo para mobile está centralizado em `apply_mobile_css()` em `utils.py`.

### Fontes de jogos
- **APIs externas:** football-data.org (ligas europeias) + ESPN (Brasileirão)
- **Jogos manuais foram removidos** — todos os jogos vêm via API.

---

## Bot Discord (`bot/bot.py`)

### Variáveis de ambiente necessárias
| Variável | Descrição |
|---|---|
| `DISCORD_TOKEN` | Token do bot (Discord Developer Portal) |
| `DISCORD_CHANNEL_ID` | ID do canal onde o bot posta notificações automáticas |
| `DATABASE_URL` | String de conexão Supabase (mesma do app) |
| `API_KEY` | Chave football-data.org (mesma do app) |
| `ODDS_API_KEY` | Chave The Odds API (mesma do app) |

Todas estão em `.streamlit/secrets.toml`.

### Slash Commands

**`/vincular <usuario> <senha>`**
- Vincula a conta do app ao Discord do usuário (necessário uma única vez)
- Valida credenciais (SHA-256) e salva o `discord_id` na tabela `usuarios`
- Operações de banco rodam em `asyncio.to_thread` para não bloquear o event loop

**`/jogos`**
- Lista os próximos jogos com horário BRT e odds (🏠 casa · ✏️ empate · ✈️ fora)
- Exibe botões interativos (`discord.ui.Button`) — um por jogo (timeout=3600s)
- Ao clicar no botão, abre um **Modal** (`discord.ui.Modal`) com campos:
  - Gols — Time da Casa
  - Gols — Time Visitante
  - Valor apostado em EC
- Ao confirmar o modal, registra o palpite e mostra confirmação com odd e lucro potencial
- Usa `edit_original_response` (não `followup.send`) para garantir que botões aparecem na primeira chamada

**`/apostar <jogo> <placar_casa> <placar_fora> <valor>`**
- Alternativa via texto com autocomplete para o campo `jogo`
- Mesma lógica e validações do modal

**`/ranking`**
- Mostra o ranking Lisan al Gaib público (não ephemeral) com embed
- Score = `total_pontos × saldo_ec`
- Exibe: medal, score, pontos, placares exatos, jogos avaliados, banca

### Tasks automáticas

**`checar_lembretes`** (a cada 15 min):
- Busca jogos `SCHEDULED` com `lembrete_enviado = FALSE` que começam entre 2h e 3h a partir de agora
- Posta embed listando quem ainda não apostou
- Marca `lembrete_enviado = TRUE`

**`checar_resultados`** (a cada 5 min):
- ESPN: chamado a cada execução (5 min); football-data.org: a cada 6 execuções (30 min) — evita estourar rate limit do plano free
- Fallback: também processa jogos já `FINISHED` no banco com `resultado_notificado = FALSE`
- Calcula pontos e EC dos palpites (`pontos IS NULL`)
- Atualiza `palpites`, `usuarios.saldo_ec`, e faz UPSERT em `jogos` com `status='FINISHED'`
- Posta embed de resultado por jogo + ranking Lisan al Gaib

**`atualizar_odds`** (a cada 3 horas):
- Busca odds via The Odds API (ligas europeias) e calcula odds do Brasileirão via standings ESPN
- Atualiza `jogos.odds_casa`, `jogos.odds_empate`, `jogos.odds_fora` para jogos `SCHEDULED`
- Roda também na inicialização do bot

> O bot não depende de ninguém clicar "Processar resultados" no app — ele processa tudo sozinho.
> Todas as queries de banco nos comandos slash usam `asyncio.to_thread` para não bloquear o event loop.

### Sync de slash commands
- Comandos sincronizados por **guild específico** (`GUILD_ID`) no `on_ready` para propagação instantânea
- Comandos globais são limpos no startup para evitar duplicatas no cliente Discord
- Ordem obrigatória: `tree.copy_global_to(guild)` → `tree.sync(guild)` → `tree.clear_commands(guild=None)` → `tree.sync()`

### Scoring e EC (espelhado de `scoring.py`)
As funções `calcular_pontos`, `calcular_ec_ganhos` e `is_surrealidade` estão duplicadas diretamente no `bot.py` para o bot rodar de forma independente.

### Tabela `jogos` — estrutura completa
| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | TEXT PK | ID da API (`"espn_401..."` ou `"537138"`) |
| `liga` | TEXT | Nome da liga |
| `casa` / `fora` | TEXT | Nomes dos times |
| `data` | TIMESTAMPTZ | Horário do jogo (UTC) |
| `logo_casa` / `logo_fora` | TEXT | URLs dos escudos |
| `gols_casa` / `gols_fora` | INTEGER | Resultado final (NULL enquanto não finalizado) |
| `odds_casa` / `odds_empate` / `odds_fora` | REAL | Odds atualizadas pela task `atualizar_odds` |
| `status` | TEXT | `'SCHEDULED'` ou `'FINISHED'` |
| `lembrete_enviado` | BOOLEAN | Controle de lembrete pré-jogo |
| `resultado_notificado` | BOOLEAN | Controle de notificação pós-jogo |
