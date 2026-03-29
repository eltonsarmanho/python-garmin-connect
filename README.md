# Garmin Connect — Integração via API

Conjunto de scripts Python para autenticar no **Garmin Connect** e consumir dados de saúde e atividades físicas sem depender de bibliotecas de terceiros.

A abordagem usa **OAuth2 via browser real (Playwright)**, contornando o bloqueio `429` que a Garmin aplica em logins programáticos.

---

## Estrutura dos arquivos

```
TesteGarmin/
├── .env                    # Credenciais e tokens (NÃO commitar no Git!)
├── requirements.txt        # Dependências Python
│
├── GenerateTokenGarmin.py  # PASSO 1 — Gera o token via browser
├── ScriptTeste.py          # Alternativa ao GenerateTokenGarmin (mesmo propósito)
│
├── ConectGarmin.py         # Módulo reutilizável — funções de conexão
├── FetchGarminData.py      # Script de consulta simples (perfil, HR, sono, atividades)
└── GarminReport.py         # Relatório completo dos últimos N dias + export JSON
```

---

## Configuração inicial

### 1. Instalar dependências

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt

# Baixar o navegador Chromium (necessário apenas na primeira vez)
playwright install chromium
```

### 2. Configurar o arquivo `.env` (opcional para `FetchGarminData.py`)

Crie um arquivo `.env` na raiz do projeto se você também for usar scripts que ainda consomem `GARTH_TOKEN`, como `GarminReport.py`:

```env
# ── Token Garmin (gerado pelo GenerateTokenGarmin.py) ──────────────
# Valor base64 contendo [oauth1_token, oauth2_token]
# Renovar quando expirar (~30 dias para o access_token, ~30 dias para o refresh)
GARTH_TOKEN=SEU_TOKEN_BASE64_AQUI

```

> **Atenção:** Nunca adicione o `.env` ao Git. Adicione ao `.gitignore`:
> ```
> .env
> garmin_report_*.json
> ```

---

## Scripts

---

### `GenerateTokenGarmin.py` / `ScriptTeste.py`

> **Propósito:** Gerar ou renovar o `GARTH_TOKEN` que vai para o `.env`.

São equivalentes. Ambos pedem email e senha no terminal, abrem um **browser Chromium real**, tentam preencher o login automaticamente e capturam o ticket SSO gerado no redirecionamento para realizar a troca OAuth1 → OAuth2. Se a Garmin exigir MFA ou confirmação extra, basta concluir no browser aberto.

**Fluxo interno:**

```
Browser (Playwright)
    └─► Preenchimento automático ou continuação manual na página SSO da Garmin
        └─► Captura do ticket ST-xxxxx na URL/conteúdo da página
            └─► get_oauth_consumer()   → busca consumer_key/secret no S3 da garth
                └─► get_oauth1_token()  → troca ticket por OAuth1 token
                    └─► exchange_oauth2() → troca OAuth1 por OAuth2 token
                        └─► Salva em ~/.garth/ e imprime GARTH_TOKEN_B64
```

**Como usar:**

```bash
python GenerateTokenGarmin.py
```

1. Informe email e senha da conta Garmin no terminal.
2. Um browser abrirá automaticamente.
3. Se necessário, conclua MFA ou validações extras.
4. O script captura o token e exibe no terminal:
   ```
   GARMIN_TOKEN_B64 (paste into GitHub secret):
   W3sib2F1dGhfdG9rZW4...
   ```
5. Copie o valor e cole no `.env` como `GARTH_TOKEN=...` caso vá usar scripts que dependem dele.

**Quando renovar?**
- O `access_token` expira em ~1 dia (campo `expires_in`).
- O `refresh_token` expira em ~30 dias (`refresh_token_expires_in`).
- Ao receber erro `401 Unauthorized`, execute o script novamente.

---

### `ConectGarmin.py`

> **Propósito:** Módulo reutilizável para outros sistemas importarem.

Contém as funções de conexão e consulta à API, prontas para serem importadas por qualquer outro script ou sistema externo.

**Funções públicas:**

| Função | Descrição | Retorno |
|---|---|---|
| `get_garmin_activities(days)` | Atividades dos últimos N dias | `{"activities": [...], "count": int}` |
| `get_garmin_activities_with_credentials(days, u, p)` | Alias de compatibilidade (ignora u/p, usa o token) | igual ao acima |
| `get_garmin_daily_summary(days)` | Resumo diário: calorias, passos, HR, Body Battery | `{"days": [...]}` |

**Exemplo de uso como módulo:**

```python
from ConectGarmin import get_garmin_activities, get_garmin_daily_summary

# Atividades dos últimos 7 dias
result = get_garmin_activities(days=7)
for act in result["activities"]:
    print(act["date"], act["type"], act["calories"], "kcal", act["hr_avg"], "bpm avg")

# Resumo diário dos últimos 30 dias
summary = get_garmin_daily_summary(days=30)
for day in summary["days"]:
    print(day["date"], day["total_kcal"], "kcal", day["steps"], "passos")
```

**Estrutura de cada atividade:**

```json
{
  "date": "2026-03-27",
  "start": "2026-03-27 10:26:27",
  "type": "hiit",
  "name": "HIIT",
  "duration_s": 5594,
  "duration_fmt": "93m14s",
  "distance_km": 0.0,
  "calories": 504,
  "bmr_calories": 80,
  "hr_avg": 112,
  "hr_max": 154,
  "vo2_max": null,
  "training_effect": 3.5,
  "steps": null
}
```

**Estrutura de cada dia (resumo):**

```json
{
  "date": "2026-03-27",
  "total_kcal": 2721.0,
  "active_kcal": 701.0,
  "bmr_kcal": 2020.0,
  "steps": 9167,
  "distance_km": 7.26,
  "hr_resting": 65,
  "hr_min": 59,
  "hr_max": 138,
  "bb_max": 6,
  "bb_min": 67
}
```

**Execução direta:**

```bash
python ConectGarmin.py        # últimos 7 dias
python ConectGarmin.py 14     # últimos 14 dias
```

---

### `FetchGarminData.py`

> **Propósito:** Serviço interativo de consulta rápida do dia atual e do dia anterior.

O script pede email e senha da conta Garmin, gera o token durante a execução usando o fluxo do `GenerateTokenGarmin.py` e consulta os dados sem ler `GARTH_TOKEN` do `.env`.

Ideal para verificar rapidamente o estado dos dados:

- Perfil do usuário (nome, display name)
- 5 atividades mais recentes (com calorias)
- Frequência cardíaca de ontem (repouso, mín, máx)
- Sono de ontem (total, profundo, leve, REM)
- Calorias do dia atual (total, ativas, BMR, passos, distância, andares)

```bash
python FetchGarminData.py
```

Fluxo:

```text
Terminal
  └─► solicita email e senha
      └─► abre browser Playwright
          └─► gera token OAuth em memória
              └─► consulta perfil, atividades, FC, sono e calorias do dia
```

---

### `GarminReport.py`

> **Propósito:** Relatório completo dos últimos N dias com export JSON.

O script mais completo. Coleta por dia:

| Métrica | Campo na API |
|---|---|
| Calorias totais / ativas / BMR | `usersummary-service` |
| Passos, distância, andares | `usersummary-service` |
| Minutos ativos (moderado / vigoroso) | `usersummary-service` |
| FC repouso, mínima, máxima | `wellness-service/dailyHeartRate` |
| Sono: total, profundo, leve, REM, acordado, score | `wellness-service/dailySleepData` |
| Stress médio e máximo | `wellness-service/dailyStress` |
| Body Battery máximo e mínimo | `wellness-service/bodyBattery` |
| HRV última noite e média semanal | `hrv-service/hrv` |
| VO2 Max e Fitness Age | `fitnessstats-service` |

Além das métricas diárias, lista todas as atividades do período com:
`tipo · distância · duração · calorias · HR médio/máximo · VO2 Max · Training Effect`

**Saída gerada:**
1. Tabela resumo no terminal
2. Detalhe completo por dia no terminal
3. Arquivo `garmin_report_Nd.json` com todos os dados estruturados

```bash
python GarminReport.py        # últimos 7 dias
python GarminReport.py 14     # últimos 14 dias
python GarminReport.py 30     # últimos 30 dias
```

**Amostra da saída:**

```
── ATIVIDADES (últimos 7 dias) ───────────────────────────
  [2026-03-27 10:26:27]  hiit                 0.00 km    93m14s   504 kcal  HR 112/154  "HIIT"
  [2026-03-24 12:33:23]  hiit                 0.00 km    74m04s   418 kcal  HR 114/147  "HIIT"
  [2026-03-23 12:40:37]  hiit                 0.00 km    75m01s   408 kcal  HR 113/150  "HIIT"
  Total: 3 atividades

── RESUMO DIÁRIO (últimos 7 dias) ────────────────────────
  DATA            KCAL   ATIV   PASS    DIST   HR  HRmx   BB
  ──────────────────────────────────────────────────────────
  2026-03-23    2577.0  557.0   8312   6.6km   60   142  N/A
  2026-03-24    2405.0  385.0   4185   3.3km   61   137  N/A
  2026-03-25    2148.0  128.0   3087   2.4km   61   114    2
  2026-03-26    2057.0   37.0    746   0.6km   62   101  N/A
  2026-03-27    2721.0  701.0   9167   7.3km   65   138    6
  2026-03-28    2020.0    N/A    N/A     N/A  N/A   N/A  N/A
  2026-03-29    1302.0   41.0   1066   0.8km   61   108    4
```

---

## Entendendo o `GARTH_TOKEN`

O token é um **JSON codificado em Base64** com dois objetos dentro de uma lista:

```
base64_decode(GARTH_TOKEN) → [ oauth1_token, oauth2_token ]
```

**oauth1_token** (posição `[0]`):
```json
{
  "oauth_token": "9f21eefb-d29a-4082-81c8-019dce68b6c0",
  "oauth_token_secret": "HZxRjbvX02RH442nrJAIkARmc6cETIBOiqc",
  "mfa_token": null,
  "domain": "garmin.com"
}
```

**oauth2_token** (posição `[1]`):
```json
{
  "access_token": "eyJhbGci...",   // JWT — usado nos headers Authorization: Bearer
  "refresh_token": "eyJyZWZ...",   // Para renovar o access_token sem novo login
  "expires_in": 86400,             // Validade do access_token em segundos (~1 dia)
  "expires_at": 1757301783,        // Timestamp Unix de expiração
  "refresh_token_expires_in": 2592000,
  "refresh_token_expires_at": 1759790874,
  "scope": "CONNECT_READ CONNECT_WRITE ..."
}
```

Os scripts usam apenas o `oauth2_token["access_token"]` no header `Authorization: Bearer <token>` de cada requisição à API do Garmin Connect.

---

## Por que usar browser (Playwright)?

A Garmin bloqueia com `HTTP 429 Too Many Requests` qualquer tentativa de login programático direto (`POST` com usuário/senha). O browser real passa por esse bloqueio porque:

1. Executa o SSO embed da Garmin igual ao app mobile/web faz.
2. Passa por verificações de CAPTCHA e cookies de sessão normalmente.
3. O ticket `ST-xxxxx` é capturado do conteúdo/URL da página após o login.

---

## Endpoints da API utilizados

| Endpoint | Dados |
|---|---|
| `/userprofile-service/socialProfile` | Perfil do usuário |
| `/usersummary-service/usersummary/daily/{user}` | Resumo diário (calorias, passos) |
| `/activitylist-service/activities/search/activities` | Lista de atividades |
| `/wellness-service/wellness/dailyHeartRate` | Frequência cardíaca |
| `/wellness-service/wellness/dailySleepData` | Dados de sono |
| `/wellness-service/wellness/dailyStress` | Nível de stress |
| `/wellness-service/wellness/bodyBattery/reports/daily` | Body Battery |
| `/hrv-service/hrv` | HRV (variabilidade cardíaca) |
| `/fitnessstats-service/fitnessStats/{user}` | VO2 Max, Fitness Age |
| `/weight-service/weight/dateRange` | Composição corporal (peso, BMI) |

---

## Observações sobre dados `N/A`

Algumas métricas retornam `N/A` dependendo do dispositivo e hábitos:

| Métrica | Motivo comum do N/A |
|---|---|
| Sono | Watch não usado durante o sono |
| HRV | Requer sono monitorado pelo watch |
| Stress | Requer monitoramento contínuo ativado |
| VO2 Max | Dispositivo não suporta (ex: modelos sem GPS em atividades) |
| Andares | Dispositivo sem altímetro barométrico |

---

## Renovar o token (passo a passo)

1. Execute o script de geração:
   ```bash
   python GenerateTokenGarmin.py
   ```
2. Faça login no browser que abrir.
3. Aguarde a mensagem `Got ticket: ST-...`
4. Copie o valor `GARMIN_TOKEN_B64` exibido no terminal.
5. Substitua o `GARTH_TOKEN` no arquivo `.env`.
6. Execute qualquer script normalmente.

---

## requirements.txt

---

## Créditos

Este projeto é baseado em código público disponibilizado pela comunidade:

- **GenerateTokenGarmin.py** — Adaptado de [coleman8er/garmin-browser-auth.py](https://github.com/coleman8er/garmin-browser-auth)
  - Implementa o fluxo de autenticação via browser Playwright para contornar bloqueios da Garmin
  - [Garth](https://github.com/matin/garth) — Inspiração para o padrão de token OAuth

A integração com a API REST do Garmin Connect foi feita seguindo as rotas documentadas internamente e descobertas pela comunidade de desenvolvedores.

---

## Licença

Este projeto é **código aberto** sob a licença **MIT**.

Você é livre para:
- ✅ Usar em projetos comerciais e privados
- ✅ Modificar e redistribuir o código
- ✅ Usar em conjunto com outras licenças

Com a única obrigação de:
- ⚠️ Incluir a licença MIT original em cópias do software

Veja o arquivo [LICENSE](LICENSE) para detalhes completos.

---

## Contribuição

Contribuições são bem-vindas! Se você encontrar bugs, quiser adicionar novas funcionalidades ou melhorar a documentação:

1. Faça um **Fork** do repositório
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um **Pull Request**
