# VRP Arbitrage — BTC Volatility Risk Premium Strategy

**Linguagem:** Python 3.10+  
**Dados:** Deribit BTC-PERPETUAL (OHLC horário) + Deribit DVOL Index (IV horário)  
**Período validado:** Mar-2021 → Abr-2026 (5,1 anos, DVOL real, sem proxy sintético)  
**Melhor resultado proxy:** CAGR 53,6%/ano, Sharpe 2,66, max drawdown -33,5%  
**Status live:** não pronto para capital real; falta validação com cadeia histórica de opções e execução ponto-a-ponto.

---

## Sumário

1. [Conceito central: o que é VRP](#1-conceito-central-o-que-é-vrp)
2. [Arquitetura do sistema](#2-arquitetura-do-sistema)
3. [Previsão de volatilidade realizada](#3-previsão-de-volatilidade-realizada)
4. [Geração do sinal VRP](#4-geração-do-sinal-vrp)
5. [Filtro de regime de mercado](#5-filtro-de-regime-de-mercado)
6. [Loop do backtest — entrada e saída](#6-loop-do-backtest--entrada-e-saída)
7. [Dimensionamento de posição (Kelly)](#7-dimensionamento-de-posição-kelly)
8. [Cálculo de PnL e stress test](#8-cálculo-de-pnl-e-stress-test)
9. [Métricas de performance](#9-métricas-de-performance)
10. [Validação walk-forward por regimes](#10-validação-walk-forward-por-regimes)
11. [Catálogo de estratégias](#11-catálogo-de-estratégias)
12. [Resultados do backtest de 5 anos](#12-resultados-do-backtest-de-5-anos)
13. [Como rodar](#13-como-rodar)
14. [Limitações e riscos](#14-limitações-e-riscos)

---

## 1. Conceito central: o que é VRP

**Volatility Risk Premium (VRP)** é a diferença entre a volatilidade implícita (IV) do mercado de opções e a volatilidade realizada (RV) do ativo subjacente:

```
VRP = IV − RV
```

Em mercados de opções, os compradores pagam um prêmio de seguro para se proteger de movimentos extremos. Esse prêmio sistemático faz com que IV > RV na maior parte do tempo. Quem vende esse prêmio lucra com a diferença — esse é o edge explorado pela estratégia.

**No BTC especificamente**, o VRP tende a ser maior do que em mercados de ações tradicionais porque:
- Demanda por proteção (hedge) contra crashes é alta
- A base de holders de longo prazo gera demanda constante por puts
- A incerteza regulatória e macroeconômica sustenta prêmio de IV elevado

A estratégia implementa um **variance swap sintético**: a posição se beneficia quando IV² − RV² > 0, ou seja, quando a variância implícita supera a variância realizada no período de holding.

---

## 2. Arquitetura do sistema

```
src/vrp_arbitrage/
├── config.py          ← BacktestConfig: todos os parâmetros da estratégia
├── data.py            ← Carregamento de OHLC e IV, cálculo de log-retornos
├── volatility.py      ← EWMA e GARCH(1,1): previsão de volatilidade realizada
├── signals.py         ← Z-score VRP, seleção de estratégia, kurtosis rolling
├── backtest.py        ← Loop principal: entradas, saídas, PnL, equity curve
├── metrics.py         ← Sharpe, Sortino, max drawdown, captura VRP, stress
├── pricing.py         ← Black-Scholes: preço, delta, vega, IV implícita
├── smile.py           ← Extração do smile de IV por moneyness (para opções reais)
├── types.py           ← Dataclasses: Trade, Position, BacktestResult, OptionLeg
├── execution.py       ← Simulação de execução maker/taker, requotes
└── quality.py         ← Diagnóstico de qualidade dos dados de opções

scripts/
├── strategy_catalog.py            ← Catálogo central de estratégias e metadados
├── regime_validation.py           ← Walk-forward por janelas com classificação de regime
├── run_strategy_profiles.py       ← Backtest completo de todos os perfis
├── fetch_extended_deribit_data.py ← Download de histórico via API Deribit
├── export_promoted_strategies.py  ← Exporta relatórios Markdown com evidência OOS
└── parameter_sweep.py             ← Varredura de parâmetros (grid search)
```

**Fluxo principal de dados:**

```
OHLC (close horário)
    │
    ├─→ log_returns → returns série horária
    ├─→ EWMA forecast → rv_ewma (vol realizada estimada)
    └─→ GARCH(1,1) forecast → rv_garch
                │
                blend: rv = w × rv_garch + (1−w) × rv_ewma
                │
IV (DVOL Index horário)
    │
    vrp_signal = IV − rv
    vrp_z = z-score(vrp_signal, janela)
                │
    Filtro de regime (RV percentile + |retorno 24h|)
                │
    Loop do backtest → entrada/saída → trades → equity curve → métricas
```

---

## 3. Previsão de volatilidade realizada

O sistema usa dois estimadores de RV que podem ser usados sozinhos ou combinados via peso `garch_weight`.

### 3.1 EWMA (Exponential Weighted Moving Average)

Estimador simples e estável. Pesa retornos recentes mais fortemente sem precisar de otimização.

```python
# volatility.py — rolling_ewma_forecast()
hourly_var = returns².ewm(span=span_hours, adjust=False).mean()
vol_anual  = sqrt(hourly_var × 365 × 24)
```

**Parâmetros:**
- `ewma_span_hours` (padrão: 48h) — meia-vida exponencial. Valores menores reagem mais rápido a choques; valores maiores são mais suaves.
- `min_annual_vol` (0.05) / `max_annual_vol` (3.0) — limites de sanidade.

A saída é a volatilidade **anualizada** prevista para o próximo período.

### 3.2 GARCH(1,1)

Modelo paramétrico que captura agrupamento de volatilidade (volatility clustering): períodos de alta vol tendem a ser seguidos por alta vol.

**Equação de variância condicional:**
```
var[t] = ω + α × r²[t−1] + β × var[t−1]
```

Onde:
- `ω` (omega) = variância de longo prazo × (1 − α − β)
- `α` (alpha) = peso do choque recente (ARCH term)
- `β` (beta) = persistência da variância (GARCH term)
- Restrição de estacionariedade: α + β < 0.999

**Fitting via Maximum Likelihood Estimation (MLE):**
```python
# Minimiza negative log-likelihood:
ll = −0.5 × Σ[ log(2π) + log(var[t]) + r[t]² / var[t] ]
```
Otimizado via L-BFGS-B com bounds: ω ∈ [1e-12, 10×σ²], α,β ∈ [0,1].

**Previsão multi-step:**
```python
# Variância condicional atual:
var_T = ω + α × r[T]² + β × var[T−1]

# Caminho de previsão (mean reversion):
long_run_var = ω / (1 − α − β)
φ = α + β

var(h) = long_run_var + (var_T − long_run_var) × φ^h

# Média da variância no horizonte H:
mean_var = mean([var(0), var(1), ..., var(H−1)])
vol_anual = sqrt(mean_var × 365 × 24)
```

**Parâmetros relevantes:**
- `garch_window_hours` (168h = 7 dias) — janela de dados para fitting
- `garch_refit_interval_hours` (72h) — frequência de re-otimização
- `forecast_horizon_hours` (168h) — horizonte de previsão

### 3.3 Blend EWMA + GARCH

```python
if garch_weight == 0.0:
    rv_forecast = ewma_forecast         # Pure EWMA (todos os candidatos validados)
elif garch_weight == 1.0:
    rv_forecast = garch_forecast        # Pure GARCH
else:
    rv_forecast = garch_weight × garch + (1 − garch_weight) × ewma
```

> **Nota importante:** Todos os candidatos validados em regime_validation usam `garch_weight=0.0` (EWMA puro). Isso elimina o tempo de warm-up do GARCH e instabilidades numéricas. As variações GARCH ficam no catálogo como pesquisa.

---

## 4. Geração do sinal VRP

### 4.1 Sinal base

```python
# backtest.py
vrp_signal    = iv_series − rv_forecast          # diferença IV − RV
vrp_z         = zscore(vrp_signal, zscore_window) # z-score rolling
vrp_entry_thr = vrp_signal.quantile(vrp_entry_quantile, window)
vrp_exit_thr  = vrp_signal.quantile(vrp_exit_quantile, window)
```

**Z-score:**
```
z[t] = (VRP[t] − média(VRP, janela)) / desvio_padrão(VRP, janela)
```

Um z-score alto indica que o prêmio de volatilidade está acima do normal histórico recente — momento mais favorável para vender vol.

### 4.2 Condição de entrada do sinal

Dois modos, controlados por `require_z_and_quantile`:

```python
z_pass = (z >= vrp_entry_z)            # z-score acima do threshold
q_pass = (vrp >= vrp_entry_quantile_threshold)  # VRP bruto acima do quantil

if require_z_and_quantile:
    sinal_ok = z_pass AND q_pass       # Mais seletivo (AND)
else:
    sinal_ok = z_pass OR q_pass        # Mais frequente (OR)
```

### 4.3 Confirmação de sinal

```python
entry_streak += 1  # conta períodos consecutivos com sinal ativo
if entry_streak < signal_confirmation_periods:
    continue       # aguarda N confirmações antes de entrar
```

Com `signal_confirmation_periods=2`, a estratégia exige sinal presente em 2 horas consecutivas antes de abrir posição. Reduz ruído de falsos positivos.

### 4.4 Edge mínimo

```python
if (entry_iv − entry_rv) < min_vrp_edge:
    continue  # VRP bruto abaixo do mínimo, não vale o custo de transação
```

Garante que só entram trades com spread IV−RV suficiente para cobrir custos.

---

## 5. Filtro de regime de mercado

Antes de qualquer entrada, o mercado passa por um filtro de regime. O objetivo é evitar entrar em posições short de vol durante períodos de alta volatilidade realizada ou de movimentos extremos — exatamente quando a posição seria mais prejudicial.

```python
# backtest.py — _market_regime_filter()
abs_24h_return = |log(close).diff(24)|           # movimento absoluto nas últimas 24h
rv_rank        = percentile_rank(rv_forecast, zscore_window)  # percentil da RV atual

regime_ok = (rv_rank <= max_rv_percentile) AND (abs_24h_return <= max_abs_24h_return)
```

**Interpretação:**
- `rv_rank <= 0.85` → só opera quando a RV atual está abaixo do seu 85º percentil histórico (regime calmo/normal)
- `abs_24h_return <= 0.12` → só opera quando o BTC não se moveu mais de 12% em 24h

Se qualquer condição falhar → **nenhuma entrada é permitida naquele hora**.

**Parâmetros por estratégia:**

| Estratégia | max_rv_percentile | max_abs_24h_return |
|---|---|---|
| alpha_return_target | 85% | 10% |
| alpha_vol_breakout_guard | **75%** | **8%** (mais restritivo) |
| alpha_defensive | 90% | 12% |
| alpha_current | 90% | 12% |

`alpha_vol_breakout_guard` tem o filtro mais apertado — opera menos, mas quase exclusivamente em regime calmo.

---

## 6. Loop do backtest — entrada e saída

O loop principal (`_run_variance_proxy` em `backtest.py`) itera hora a hora sobre o OHLC e mantém estado de uma única posição aberta por vez.

### 6.1 Checklist de entrada (sem posição aberta)

```
1. Horário permitido?          (entry_start_time / entry_end_time)
2. Fora do cooldown?           (cooldown_until após último trade)
3. Regime ok?                  (_market_regime_filter)
4. Sinal ok?                   (_entry_signal_pass — z-score ou quantil)
5. Confirmação acumulada?      (entry_streak >= signal_confirmation_periods)
6. Edge bruto suficiente?      (entry_iv − entry_rv >= min_vrp_edge)
7. Notional calculado?         (_kelly_sized_notional)
8. Stress dentro do limite?    (_risk_cap_multiplier)
9. Notional acima do mínimo?   (notional >= min_contracts)
10. Edge esperado positivo?    (notional × VRP² − custo > 0)
```

Se todas passam → posição aberta, estado registrado:
```python
open_entry = {
    "entry_time": ts,
    "entry_iv":   iv_agora,
    "entry_rv":   rv_agora,
    "notional":   notional,
    "cost":       notional × variance_trade_cost × 2  # round-trip
}
```

### 6.2 Checklist de saída (com posição aberta)

```python
hold_hours = (ts − entry_time).horas

# Saída por tempo máximo
if hold_hours >= max_holding_hours:
    exit_due = True

# Saída por z-score baixo (spread VRP esgotado)
if vrp_z[ts] <= vrp_exit_z:
    exit_due = True

# Saída por quantil baixo (VRP abaixo do limiar de saída)
if vrp_atual <= vrp_exit_quantile_threshold:
    exit_due = True
```

`max_holding_hours=6` nos candidatos validados — posições muito curtas, capturando VRP intraday. Isso reduz exposição a saltos de preço noturnos.

### 6.3 Cálculo do PnL ao fechar

```python
returns_slice = log_returns[entry_time : exit_time]
realized_vol  = std(returns_slice, ddof=1) × sqrt(365 × 24)  # anualizado

pnl = notional × (entry_iv² − realized_vol²) − cost
cash += pnl
```

**Intuição:** A posição lucra quando a variância implícita (IV²) supera a variância realizada no período de holding (RV²). O PnL é **proporcional ao notional** e à **diferença de variâncias**.

Após saída: `cooldown_until = ts + cooldown_hours` — impede re-entrada imediata.

---

## 7. Dimensionamento de posição (Kelly)

### 7.1 Fórmula do notional Kelly

```python
# backtest.py — _kelly_sized_notional()
edge_variance = max(iv² − rv², 0)       # vantagem esperada (variance domain)
risk_variance = max(rv², 1e-6)           # risco (variância realizada)

raw_kelly = kelly_fraction × (edge_variance / risk_variance)

min_mult = min_contracts / base_contracts
max_mult = max_contracts / base_contracts
multiplier = clip(raw_kelly, min_mult, max_mult)

notional = variance_notional × multiplier
```

**Interpretação:**
- `edge_variance / risk_variance` é a fração ótima de Kelly clássica aplicada ao universo de variâncias
- `kelly_fraction=0.75` usa 75% do Kelly ótimo (fractional Kelly) — reduz risco de ruin
- O resultado é clipado entre `min_contracts` e `max_contracts`

**Exemplo numérico:**
```
IV = 0.70 (70% anualizado), RV = 0.50 (50%)
edge_variance = 0.70² − 0.50² = 0.49 − 0.25 = 0.24
risk_variance = 0.50² = 0.25
raw_kelly = 0.75 × (0.24 / 0.25) = 0.72
notional = 180 × 0.72 = 129.6
```

Em ambiente de alta volatilidade com VRP grande, o Kelly aumenta o notional automaticamente.

### 7.2 Cap por stress

Após o Kelly, o notional é reduzido se o stress test ultrapassar o limite:

```python
# Calcula perda em stress (crash de 20% + choque de vol de 35%)
unit_stress = _variance_stress_pnl(entry_iv, notional, config)

# Cap proporcional:
max_loss_permitida = initial_capital × max_trade_stress_loss_pct
if |stress_loss| > max_loss_permitida:
    notional × = max_loss_permitida / |stress_loss|
```

Para `alpha_return_target`: max stress = 10.000 × 12% = $1.200 por trade.  
Para `alpha_defensive`: max stress = 10.000 × 6% = $600 por trade.

---

## 8. Cálculo de PnL e stress test

### 8.1 PnL do variance proxy

```
PnL = notional × (IV_entrada² − RV_realizada²) − custo_round_trip
```

O custo inclui simulação de bid-ask:
```
custo = notional × variance_trade_cost × 2.0
```
Com `variance_trade_cost=0.0008`: custo de 0.16% do notional por trade (round-trip).

### 8.2 Stress test de um trade

```python
# _variance_stress_pnl()
# Cenário: crash de 20% em 4h → RV realizada dispara → posição perde

hourly_gap = log(0.80) / 4 horas = −5.57%/hora por 4h
stressed_rv = std(returns_do_crash) × sqrt(365 × 24)

# Choque adicional de volatilidade implícita:
stressed_exit_vol = max(stressed_rv, entry_iv + 0.35)

stress_pnl = notional × (entry_iv² − stressed_exit_vol²)
# Tipicamente negativo — é a perda máxima estimada por trade
```

**Cenário concreto:**
```
entry_iv = 0.70, notional = 130
stressed_exit_vol ≈ 0.70 + 0.35 = 1.05 (choque de 35% na vol)
stress_pnl = 130 × (0.49 − 1.1025) = 130 × (−0.6125) = −79.6
```

### 8.3 Stress de posição em opções reais

Para posições de opções (não variance proxy):
```python
# _position_stress_pnl()
spot_stressado = entry_spot × 0.80    # queda de 20%
vol_stressada  = max(entry_iv + 0.35, entry_iv × 1.5)

# Reprecia cada leg com Black-Scholes no cenário estressado
pnl_stress = Σ [sign × BS(spot_stressado, strike, tempo, vol_stressada)]
```

---

## 9. Métricas de performance

Todas calculadas em `metrics.py` e `backtest.py — _equity_result()`.

| Métrica | Fórmula | Interpretação |
|---|---|---|
| **Total PnL** | equity_final − capital_inicial | Lucro absoluto no período |
| **Total Return** | PnL / capital_inicial | Retorno sobre capital de $10k |
| **Sharpe** | (μ_retornos / σ_retornos) × √(8760) | Risk-adjusted return anualizado (hourly) |
| **Sortino** | (μ / σ_downside) × √(8760) | Como Sharpe mas penaliza só downside |
| **Max Drawdown** | min((equity − cummax) / cummax) | Pior queda de pico para vale |
| **Win Rate** | trades_positivos / total_trades | Taxa de acerto por trade |
| **Profit Factor** | Σgains / Σlosses | Razão lucros/prejuízos brutos |
| **VRP Capture** | PnL_realizado / VRP_teórico_total | % do prêmio teórico capturado |
| **Stress/PnL** | \|stress_gap_pnl\| / \|total_pnl\| | Razão exposição tail risk / lucro |

**VRP Capture Efficiency** — detalhe:
```python
# Para cada trade:
theoretical += max(vrp_at_entry, 0) × abs(notional)

capture_efficiency = Σ(pnl_trades) / theoretical
```
Um capture de 0.30 significa que a estratégia realizou 30% do prêmio teórico disponível (o restante foi consumido por timing ruim, custos e saídas antecipadas).

---

## 10. Validação walk-forward por regimes

Para evitar overfitting, a estratégia é validada em janelas **estritamente out-of-sample** usando walk-forward com classificação de regime de mercado.

### 10.1 Configuração das janelas

```
train_days = 60   (janela de aquecimento da estratégia)
test_days  = 30   (janela OOS, nunca vista no treino)
step_days  = 15   (deslocamento a cada fold)

Resultado: 119 folds sobre 5.1 anos de DVOL real
```

```
Fold 0:  [Mar-2021 ... Mai-2021] train | [Mai-2021 ... Jun-2021] test
Fold 1:  [Abr-2021 ... Jun-2021] train | [Jun-2021 ... Jul-2021] test
...
Fold 118: [Dez-2025 ... Fev-2026] train | [Fev-2026 ... Mar-2026] test
```

### 10.2 Seletor walk-forward

Em cada fold, os candidatos competem no período de **treino** após 14 dias de warm-up e o vencedor é testado no OOS:

```python
# Objetivo de seleção:
score = PnL − 0.02 × |stress_loss| − 5000 × |max_drawdown| + 4 × vrp_capture

# Penalidades:
# -0.02 por unidade de perda em stress    → proteção de tail risk
# -5000 por 1.0 de drawdown             → penalidade severa a drawdowns
# +4 por unidade de captura VRP          → premia eficiência do sinal
```

O candidato selecionado **não vê o período de teste** — a seleção é puramente baseada no treino.

### 10.3 Classificação de regime

Cada janela de teste recebe uma label de regime:

```python
if rv >= 0.75 OR |retorno_24h_max| >= 0.12:
    regime = "volatile"   # BTC em modo extremo (crash, rally violento)
elif |retorno_total_30d| >= 0.12:
    regime = "trending"   # Tendência clara no período
else:
    regime = "calm"        # Mercado lateral ou de baixa volatilidade
```

**Distribuição nos 119 folds (5.1 anos):**
- calm: 62 janelas (52%)
- volatile: 30 janelas (25%)
- trending: 27 janelas (23%)

### 10.4 Outputs gerados

```
data/results/regime_validation_5y/
├── candidate_windows.csv      ← métricas de cada candidato em cada fold
├── walk_forward_selector.csv  ← candidato selecionado e PnL OOS por fold
├── regime_validation_report.md
└── latest_<candidato>_*.csv   ← equity/trades/métricas do último fold
```

---

## 11. Catálogo de estratégias

Todas as configs centralizam em `scripts/strategy_catalog.py`. Cada entrada tem:

```python
@dataclass
class StrategyEntry:
    name: str               # identificador único
    config: BacktestConfig  # parâmetros completos
    risk_bucket: str        # conservative | balanced | aggressive | research
    validate: bool          # se True, entra no regime_validation
    oos_evidence: dict      # evidência OOS preenchida após validação
```

### 11.1 Candidatos validados (validate=True)

Todos usam EWMA puro (`garch_weight=0.0`), z-score window de 72h, confirmação em 2 períodos, cooldown de 3h e max_holding de 6h. As diferenças são em notional, filtros de regime e tolerância a stress.

---

#### `alpha_return_target` — Aggressive

**Propósito:** Candidato primário de pesquisa. Notional alto + filtro de regime apertado para máxima captura de VRP no proxy.

| Parâmetro | Valor | Efeito |
|---|---|---|
| `variance_notional` | **180.0** | Base de sizing (maior de todos os candidatos) |
| `kelly_fraction` | 0.75 | 75% do Kelly ótimo |
| `max_trade_stress_loss_pct` | **0.12** | Permite perda de até 12% do capital por trade em stress |
| `min_vrp_edge` | **0.030** | Mínimo de 3% de VRP bruto para entrar |
| `max_rv_percentile` | **0.85** | Opera apenas quando RV abaixo do 85º percentil |
| `max_abs_24h_return` | **0.10** | Bloqueia se BTC moveu >10% em 24h |
| `vrp_entry_z` | 0.35 | Z-score de entrada baixo → entra com frequência |
| `require_z_and_quantile` | False | OR lógico → mais entradas |

**Evidência corrigida (5.1 anos, proxy DVOL):**
- Backtest contínuo: CAGR 53,6%/ano, Sharpe 2,66, max drawdown -33,5%
- Walk-forward: 119 janelas OOS de 30 dias com passo de 15 dias, portanto sobrepostas
- 89,1% das janelas sobrepostas positivas
- Pior janela: -2.281 no fold 27

---

#### `alpha_vol_breakout_guard` — Balanced

**Propósito:** Variante com filtro de regime mais restritivo. Menor frequência de trades, maior taxa de acerto.

| Parâmetro | Diferença vs alpha_current | Efeito |
|---|---|---|
| `variance_notional` | 120.0 (vs 100) | Ligeiramente maior |
| `max_rv_percentile` | **0.75** | Só opera no 75º percentil de RV (mais seletivo) |
| `max_abs_24h_return` | **0.08** | Bloqueia se BTC moveu >8% em 24h (mais restritivo) |
| `min_vrp_edge` | 0.030 | Igual ao alpha_return_target |
| `max_trade_stress_loss_pct` | 0.08 | Moderado |

**Evidência OOS:**
- Backtest contínuo: CAGR 43,7%/ano, Sharpe 3,01, max drawdown -24,0%
- Walk-forward: 89,1% das janelas sobrepostas positivas
- Min PnL em janela: -897

> Variante de menor risco relativo dentro do proxy, ainda sem validação para execução live.

---

#### `alpha_plus` — Balanced

**Propósito:** Upgrade moderado do baseline. Notional intermediário entre alpha_current e alpha_return_target.

| Parâmetro | Diferença vs alpha_current |
|---|---|
| `variance_notional` | 150.0 (vs 100) |
| `max_trade_stress_loss_pct` | 0.10 (vs 0.08) |

**Evidência OOS:**
- Backtest contínuo: CAGR 48,7%/ano, Sharpe 2,78, max drawdown -29,1%
- Walk-forward: 86,6% das janelas sobrepostas positivas
- Min PnL em janela: -1.525

---

#### `alpha_current` — Balanced (baseline)

**Propósito:** Linha de base para comparação. Parâmetros conservadores, notional padrão de 100.

```python
# Parâmetros base (todos os candidatos EWMA herdam daqui):
garch_weight           = 0.0   # EWMA puro
ewma_span_hours        = 48    # 48h de span exponencial
zscore_window          = 72    # 72h para z-score e quantis
vrp_entry_z            = 0.35  # z-score de entrada
vrp_exit_z             = 0.20  # z-score de saída
min_vrp_edge           = 0.025 # 2.5% de VRP mínimo
require_z_and_quantile = False  # OR lógico
signal_confirmation_periods = 2
cooldown_hours         = 3
max_holding_hours      = 6
variance_notional      = 100.0
kelly_fraction         = 0.75
max_contracts          = 1000.0
max_trade_stress_loss_pct = 0.08
max_rv_percentile      = 0.90
max_abs_24h_return     = 0.12
vrp_entry_quantile     = 0.60
variance_trade_cost    = 0.0008
```

**Evidência OOS:**
- Backtest contínuo: CAGR 39,2%/ano, Sharpe 3,11, max drawdown -20,6%
- Walk-forward: 86,6% das janelas sobrepostas positivas

---

#### `alpha_defensive` — Conservative

**Propósito:** Menor risco absoluto. Notional reduzido, edge mínimo mais alto.

| Parâmetro | Diferença vs alpha_current |
|---|---|
| `variance_notional` | **90.0** (menor) |
| `min_vrp_edge` | **0.035** (3.5% mínimo — mais seletivo) |
| `max_trade_stress_loss_pct` | **0.06** (cap de 6%) |

**Evidência OOS:**
- Backtest contínuo: CAGR 36,8%/ano, Sharpe 3,21, max drawdown -18,8%
- Walk-forward: 87,4% das janelas sobrepostas positivas
- Menor drawdown contínuo entre os candidatos validados

> Variante mais conservadora do proxy, mas ainda sem validação de execução real.

---

#### `alpha_carry_confirmed` — Research (eliminado)

**Propósito original:** Testar confirmação mais rigorosa do sinal com AND lógico + holding mais longo.

| Parâmetro | Valor |
|---|---|
| `require_z_and_quantile` | **True** (AND lógico — muito mais restritivo) |
| `vrp_entry_quantile` | **0.70** (70º percentil, mais alto) |
| `max_holding_hours` | **12** (vs 6) |
| `signal_confirmation_periods` | 1 |

**Resultado OOS:** Inferior aos principais candidatos. No cálculo corrigido, o backtest contínuo fica com CAGR 26,3%, Sharpe 1,74, max drawdown -26,4% e pior stress/pnl. A combinação de filtro AND + holding mais longo gerou trades mais esparsos com tail risk maior.

**Status: Não promovido. Não recomendado.**

---

### 11.2 Perfis de pesquisa (validate=False, sem evidência OOS)

Estes perfis existem no catálogo como referência e são rodados via `run_strategy_profiles.py`, mas **não foram incluídos no regime_validation** por usarem GARCH (instabilidade no warm-up curto das janelas).

#### `adaptive_alpha` — Balanced

Blend leve de GARCH (35%). Objetivo: testar se adicionar um pouco de GARCH melhora o sinal sobre EWMA puro.

```python
garch_weight  = 0.35   # 35% GARCH, 65% EWMA
variance_notional = 100.0
```

#### `conservative` — Conservative

GARCH dominante (70%), notional mínimo (1.0), Kelly fracionado (0.4). Serve como sanity check — se essa variante não gera retorno, os dados têm problema.

```python
garch_weight  = 0.70
variance_notional = 1.0
kelly_fraction    = 0.40
max_contracts     = 10.0
max_holding_hours = 72    # 3 dias
```

#### `balanced_garch` — Balanced

GARCH 65%, notional moderado (10.0), z-score de entrada mais relaxado (0.6).

#### `high_return` — Aggressive

GARCH 70% + Kelly completo (1.0) + notional 100. Combina GARCH com sizing agressivo para testar o limite de retorno com o modelo paramétrico.

#### `max_return` — Research

Sem limites práticos: Kelly 1.0, notional 150, cooldown 2h, stress tolerance 20%. Serve para medir o teto teórico de retorno — não para produção.

#### `overtrade_aggressive` — Research

Stress test de frequência: cooldown 0, confirmação 1, edge mínimo 0.5% (quase sem filtro). Mostra o comportamento do sistema quando forçado a operar com máxima frequência.

---

## 12. Resultados corrigidos do backtest de 5 anos

**Período:** Mar-2021 → Abr-2026 | **Dados:** DVOL real Deribit | **Capital inicial:** $10.000  
**Importante:** estes resultados são de proxy DVOL/variance, não de execução real com opções.

### 12.1 Backtest contínuo proxy

| Estratégia | Capital Final | Lucro Total | CAGR | Pior mês | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| alpha_return_target | **$89.362** | **$79.362** | **53,6%** | -26,8% | -33,5% | 2,66 |
| alpha_plus | $75.734 | $65.734 | 48,7% | -22,7% | -29,1% | 2,78 |
| alpha_vol_breakout_guard | $63.504 | $53.504 | 43,7% | -18,7% | -24,0% | 3,01 |
| alpha_current | $54.120 | $44.120 | 39,2% | -15,7% | -20,6% | 3,11 |
| alpha_defensive | $49.476 | $39.476 | 36,8% | -14,4% | -18,8% | 3,21 |

### 12.2 Walk-forward OOS

Janelas de 30 dias com passo de 15 dias são **sobrepostas**. O `Overlap PnL Sum` é diagnóstico, não uma curva de capital realizável.

| Estratégia | Win | Overlap PnL Sum | Even Non-Overlap PnL | Avg Ret% | Med Ret% | Sharpe | % Pos | Min PnL |
|---|---|---|---|---|---|---|---|---|
| alpha_return_target | 119 | 162.294 | 81.018 | 13,64% | 7,81% | 3,73 | 89,1% | -2.281 |
| alpha_plus | 119 | 134.295 | 67.048 | 11,29% | 6,54% | 3,72 | 86,6% | -1.525 |
| alpha_vol_breakout_guard | 119 | 109.388 | 54.608 | 9,19% | 5,20% | 3,74 | 89,1% | -897 |
| alpha_current | 119 | 90.124 | 44.996 | 7,57% | 4,36% | 3,70 | 86,6% | -1.017 |
| alpha_defensive | 119 | 80.411 | 40.098 | 6,76% | 3,87% | 3,64 | 87,4% | -893 |
| alpha_carry_confirmed | 119 | 48.802 | 23.763 | 4,10% | 2,82% | 2,77 | 80,7% | -2.262 |

*Avg Ret% é média por janela sobreposta, cada janela reiniciando capital em $10k.

### 12.3 PnL por regime (alpha_return_target)

| Regime | Janelas | Overlap PnL Sum | Avg PnL | % Positivo |
|---|---|---|---|---|
| calm | 62 (52%) | 93.203 | 1.503 | 93,5% |
| trending | 27 (23%) | 32.678 | 1.210 | 81,5% |
| volatile | 30 (25%) | 36.413 | 1.214 | 86,7% |

O proxy segue positivo no agregado dos três regimes, mas há janelas individuais negativas em todos os regimes. Isso não elimina risco de cauda.

### 12.4 Walk-forward selector

O seletor automático (escolhe o candidato com melhor score no treino e testa no OOS seguinte):
- **Overlap PnL Sum: 144.643** (87,4% das janelas positivas)
- **Even non-overlap PnL: 72.225**
- `alpha_return_target` selecionado em 80 de 119 folds

### 12.5 Interpretação para live test

O resultado proxy é forte, mas ainda não deve ser tratado como rentabilidade live. O gargalo principal é microestrutura: tamanho mínimo, spread, margem e PnL executável das pernas reais.

| Capital | Uso recomendado | Observação |
|---|---|---|
| R$1k | Teste operacional | Bom para API, logs, coleta de dados e ordens simbólicas; ruim para medir rentabilidade. |
| R$2k | Live test simbólico | Ainda sofre com spread, margem e granularidade. |
| R$5k | Mínimo aceitável | Começa a permitir sizing mais controlado. |
| R$10k+ | Teste live mais saudável | Melhor para avaliar execução sem distorção extrema de custos. |

Regras práticas antes de arriscar capital:

- Não vender opção descoberta com capital pequeno.
- Usar estruturas com perda máxima definida quando possível.
- Limitar risco por trade a 0,25%-0,50% do capital.
- Não operar se o spread consumir parte relevante do prêmio.
- Rodar o pipeline executável de opções antes de aumentar tamanho.
- Coletar snapshots de cadeia de opções por tempo suficiente para medir liquidez real.

O repo já tem um gate para isso:

```bash
python scripts/run_executable_options_backtest.py
```

Com os dados atuais, o gate passa microestrutura de snapshot recente, mas ainda bloqueia live por falta de histórico suficiente.

---

## 13. Como rodar

### 13.1 Instalar dependências

```bash
pip install pandas numpy scipy requests
```

### 13.2 Baixar dados históricos

```bash
# 8 anos de OHLC + 5 anos de DVOL real (Deribit, gratuito)
python scripts/fetch_extended_deribit_data.py \
  --start-date 2018-08-15 \
  --dvol-start-date 2021-03-24 \
  --ohlc-file data/extended/btc_1h_8y.csv \
  --dvol-file data/extended/btc_dvol_1h_5y.csv
```

> **Bug corrigido:** Versões anteriores usavam `resolution=60` (segundos) na API DVOL,
> que retorna zero linhas. O correto é `resolution=3600` (1 hora). Já corrigido em
> `deribit_api.py`.

### 13.3 Rodar validação walk-forward (5 anos)

```bash
python scripts/regime_validation.py \
  --ohlc data/extended/btc_1h_8y.csv \
  --iv   data/extended/btc_dvol_1h_5y.csv \
  --train-days 60 \
  --test-days  30 \
  --step-days  15 \
  --output-dir data/results/regime_validation_5y
```

Gera ~119 folds, demora ~5-10 minutos.

### 13.4 Exportar relatórios Markdown

```bash
python scripts/export_promoted_strategies.py
# Saída:
#   data/results/reports/promoted_strategies.md
#   data/results/reports/strategy_comparison.md
```

### 13.5 Rodar backtest completo de todos os perfis

```bash
python scripts/run_strategy_profiles.py
# Usa data/btc_1h.csv e data/btc_dvol_1h.csv (dados curtos locais)
# Para usar os dados estendidos, edite as paths em main()
```

### 13.6 Rodar backtest executável com opções reais

Este comando **não usa DVOL proxy** e **não cai em fallback sintético**. Ele exige histórico point-in-time de cadeia de opções com bid/ask, tamanhos, greeks, IV, volume e open interest.

```bash
python scripts/run_executable_options_backtest.py \
  --ohlc data/extended/btc_1h_8y.csv \
  --options data/deribit_option_snapshots.csv \
  --output-dir data/results/executable_options
```

Se o histórico de opções não existir ou tiver cobertura insuficiente, o script falha e grava:

```text
data/results/executable_options/executable_options_gate.md
```

Para começar a montar histórico daqui para frente:

```bash
python scripts/collect_deribit_option_snapshot.py --append --repeat 1
```

---

## 14. Limitações e riscos

### 14.1 O que o backtest captura bem

- VRP estrutural do BTC ao longo de múltiplos regimes de mercado
- Comportamento across bull run 2021, bear 2022, recuperação 2023-2024
- Robustez de parâmetros via walk-forward genuíno (sem lookahead)
- Tail risk estimado via stress test (crash de 20% + choque de vol de 35%)

### 14.2 O que o backtest não captura

| Risco | Descrição |
|---|---|
| **Execução real** | O repo agora tem runner executável de opções, margem e gates de dados, mas o backtest de 5 anos ainda usa variance proxy porque não há cadeia histórica de opções no repo. |
| **Liquidez** | Com $10k o impacto de mercado é negligível. Com $100k+, abrir e fechar posições de opções BTC moveria o mercado, especialmente em strikes OTM. |
| **Gamma risk** | Posições short de volatilidade têm gamma negativo — em movimentos abruptos intraday, a posição piora antes que o filtro de regime consiga bloquear novas entradas (posições abertas não são fechadas pelo filtro). |
| **Concentração temporal** | Os retornos são concentrados em 2021-2022 (VRP excepcionalmente alto). Nos dados de 2025-2026, o VRP é menor e os retornos mais modestos. |
| **DVOL como proxy** | O índice DVOL da Deribit agrega IV de todas as opções BTC negociadas. A estratégia usa DVOL como substituto de IV sem distinção de strike/expiry — ignora o smile de volatilidade. |
| **Margem** | O backtest executável inclui um modelo conservador de margem/liquidação, mas ainda precisa ser calibrado contra as regras reais da Deribit antes de produção. |

### 14.3 Interpretação dos números de retorno

```
CAGR de 53,6%/ano (alpha_return_target) é relativo a $10.000 de capital.
Isso assume que $10.000 é o capital total necessário para suportar as posições.

Mais conservadoramente:
- Capital at-risk por trade (max stress) ≈ $1.200
- Com esse denominador, o retorno mensal seria ~130%/mês → claramente superestimado

O número mais honesto é o retorno **em relação ao capital de margem real**
exigido pela corretora para manter short vega em BTC options.
```

### 14.4 Seleção de parâmetros

Os parâmetros foram desenvolvidos com conhecimento do período histórico. Mesmo com walk-forward, a **escolha dos candidatos** foi informada pelos resultados. Um teste verdadeiramente out-of-sample só seria possível em dados futuros (live trading paper/real).

---

## Referências

- **Deribit DVOL Index:** Metodologia em [deribit.com/dvol](https://www.deribit.com/dvol)
- **Variance Swaps:** Demeterfi, Derman et al. (1999) — *More Than You Ever Wanted to Know About Volatility Swaps*
- **VRP em Crypto:** Alexander & Imeraj (2023) — *Delta Hedging Bitcoin Options with a Smile*
- **GARCH(1,1):** Bollerslev (1986) — *Generalized Autoregressive Conditional Heteroskedasticity
- **Kelly Criterion:** Kelly (1956) — *A New Interpretation of Information Rate*
- **Walk-Forward Validation:** Pardo (2008) — *The Evaluation and Optimization of Trading Strategies*
