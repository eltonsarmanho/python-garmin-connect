# Garmin Connect — Integração via API

Conjunto de scripts Python para autenticar no **Garmin Connect** e consumir dados de saúde e atividades físicas.

A autenticação usa a biblioteca oficial **[`garminconnect`](https://github.com/cyberjunky/python-garminconnect)** (cyberjunky), que implementa o mesmo fluxo SSO mobile da Garmin, obtendo tokens OAuth DI nativos. Os tokens são salvos localmente e reutilizados automaticamente — sem necessidade de browser ou `.env`.

---

## Estrutura dos arquivos

```
python-garmin-connect/
├── requirements.txt            # Dependências Python
│
├── GenerateTokenGarmin.py      # PASSO 1 — Autentica e salva tokens em ~/.garminconnect
├── FetchGarminData.py          # Consulta rápida: perfil, atividades, FC, sono, calorias do dia
└── GarminReport.py             # Relatório completo dos últimos N dias + export JSON
```

---

## Configuração inicial

### 1. Criar e ativar o ambiente virtual

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

> **Não é necessário** instalar Playwright, browser Chromium, `.env` ou nenhum token manual.

---

## Scripts

---

### `GenerateTokenGarmin.py`

> **Propósito:** Autenticar na Garmin com email e senha, e salvar os tokens localmente para reutilização.

Usa a biblioteca `garminconnect` para realizar o login via fluxo SSO mobile nativo da Garmin. Os tokens são salvos em `~/.garminconnect/` e reaproveitados automaticamente nas próximas execuções — sem necessidade de logar novamente.

Suporta **MFA/2FA**: se a conta exigir código de autenticação, o script solicitará no terminal.

**Fluxo interno:**

```
Terminal (email + senha)
    └─► garminconnect.Garmin.login()
        └─► SSO mobile da Garmin (curl_cffi)
            └─► Tokens OAuth DI salvos em ~/.garminconnect/
                └─► Sessão pronta para uso pelos demais scripts
```

**Como usar:**

```bash
python GenerateTokenGarmin.py
```

1. Informe email e senha da conta Garmin.
2. Se a conta tiver MFA ativo, informe o código quando solicitado.
3. Os tokens são salvos automaticamente em `~/.garminconnect/`.
4. Na próxima execução, a sessão é retomada dos tokens salvos, sem pedir credenciais.

**Quando reautenticar?**
- Os tokens DI incluem refresh token. O script os renova automaticamente enquanto o refresh token for válido (~90 dias).
- Se receber erro `401 Unauthorized`, execute o script novamente para fazer um novo login.

---

### `FetchGarminData.py`

> **Propósito:** Consulta rápida e interativa dos dados do dia atual e do dia anterior.

Pede email e senha no terminal, tenta retomar a sessão salva em `~/.garminconnect/` e — caso não exista — realiza um novo login. Exibe no terminal:

- Nome do usuário autenticado
- Resumo do dia atual (calorias total/ativas/BMR, passos, distância, andares)
- 5 atividades mais recentes (tipo, distância, duração, calorias)
- Frequência cardíaca de ontem (repouso, mínima, máxima)
- Sono de ontem (total, profundo, leve, REM, acordado)

```bash
python FetchGarminData.py
```

Fluxo:

```text
Terminal (email + senha)
  └─► Tenta retomar sessão de ~/.garminconnect/
      └─► Se inválida: novo login via garminconnect.Garmin.login()
          └─► Tokens salvos em ~/.garminconnect/
              └─► Consulta perfil, atividades, FC, sono e resumo do dia
```

---

### `GarminReport.py`

> **Propósito:** Relatório completo dos últimos N dias com export JSON.

> **Atenção:** Este script ainda usa autenticação via `GARTH_TOKEN` no `.env` (fluxo legado). Para integrá-lo ao novo fluxo, substitua a função `load_token()` pela função `authenticate()` do `FetchGarminData.py`.

O script mais completo. Coleta por dia:

| Métrica | Endpoint da API |
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

## Como a autenticação funciona

A biblioteca `garminconnect` utiliza o mesmo fluxo de autenticação SSO mobile da Garmin:

1. Login via `curl_cffi` simulando o app Android da Garmin Connect
2. Obtenção de tokens **DI OAuth** nativos (não mais OAuth1 + troca manual)
3. Tokens salvos localmente em `~/.garminconnect/garmin_tokens.json`
4. Nas próximas execuções, os tokens são carregados e renovados automaticamente via refresh token

Os avisos `mobile+cffi returned 429` e `mobile+requests returned 429` são normais durante o login — a lib testa diferentes métodos de forma automática antes de encontrar um que funcione.

---

## Tokens — onde ficam salvos

```
~/.garminconnect/
└── garmin_tokens.json    # access_token + refresh_token + expiração
```

- **Validade do access token:** ~1 hora (renovado automaticamente)
- **Validade do refresh token:** ~90 dias
- Após 90 dias sem uso, execute `GenerateTokenGarmin.py` novamente para novo login

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

## requirements.txt

```
requests
python-dotenv
garminconnect
curl_cffi
```

---

## Créditos

Este projeto é baseado em:

- **[cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect)** — biblioteca Python para autenticação e acesso à API Garmin Connect, implementando o fluxo SSO mobile nativo com tokens DI OAuth.

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
