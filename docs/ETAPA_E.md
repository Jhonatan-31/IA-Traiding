# Etapa E — Informe técnico

## Arquitectura

```
Binance public OHLCV (closed only)
        ↓
ml-train job (offline profile)
  dataset → features → labels → walk-forward → artifact
        ↓
PostgreSQL (ml_datasets, ml_models, ml_predictions, ml_runtime)
        ↓
FastAPI /api/ml/*  +  Shadow AI (log only)
        ↓
Dashboard React /ai
```

Flujo de señal (obligatorio):

`Modelo → señal propuesta → estrategia → riesgo → simulador`

En **SHADOW_AI** el flujo se corta en el registro: **no hay órdenes paper ni real**.

## Objetivo

`P(net return > 0 en las próximas 6 velas 1h)` con fee 0.1% + slip 0.1% ida y vuelta (~0.4% round-trip).

Limitaciones: sin profundidad de libro, fills ilustrativos, etiqueta solo para train/eval (nunca como feature).

## Resultados walk-forward (run real)

- Dataset: 15 símbolos × ~800 barras 1h = **12000** filas; muestras etiquetadas **11175**
- Modelo: HistGradientBoostingClassifier `v20261103T192011Z`
- Hash: `86de2633faeb6a7a89ad0ff612a8f121107fc7a5968b1af8293dee80d87c7252`
- Mean ROC-AUC HGB: **0.5497**
- Mean ROC-AUC naive: **0.5000**
- Baselines: LogisticRegression, naive prior, SMA10/50 proxy
- Validado investigación: **sí**
- Validado PAPER_AI: **no** (nunca auto)
- Políticas simuladas en folds: mayormente **net_return negativo** (costos). **No se afirma rentabilidad.**

## Endpoints ML

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/api/ml/status` | Estado, modelo, métricas |
| GET | `/api/ml/predictions` | Historial Shadow |
| GET | `/api/ml/comparison` | Walk-forward vs baselines |
| POST | `/api/ml/shadow/run` | Generar predicciones (sin órdenes) |

## Pruebas

24 passed (17 Etapa D + ML pipeline).

## Captura

`docs/screenshots/etapa-e-ai.png`

## Rollback

```powershell
git checkout checkpoint-pre-etapa-e
docker compose up -d --build
# Nunca down -v
```

Reentrenar:

```powershell
docker compose --profile ml run --rm ml-train
```
