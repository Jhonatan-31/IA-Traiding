# Etapa S — Sistema de diseño (S1–S2)

## Identidad

**AI Trading Bot Pro — Professional Crypto Trading Terminal (Premium Edition)**

Modo visible: SIMULACIÓN. Sin dinero real.

## Tokens (`frontend/src/styles.css`)

| Token | Valor |
|---|---|
| `--bg` | `#0B1020` |
| `--bg-elevated` | `#111827` |
| `--bg-soft` | `#172033` |
| `--border` | `#273247` |
| `--text` | `#F3F6FB` |
| `--muted` | `#9CAAC0` |
| `--brand` | `#4F8CFF` |
| `--buy` | `#17B890` |
| `--sell` | `#F05A68` |
| `--warn` | `#EAB85D` |

Tipografía: Inter + JetBrains Mono (números tabulares).

## Navegación

1. Inicio `/`
2. Mercado en vivo `/mercado` (alias `/charts`)
3. Bot Demo `/demo`
4. Movimientos `/movimientos` (alias `/trades`)
5. Mis posiciones `/posiciones`
6. Resultados `/resultados` (alias `/performance`)
7. Análisis IA `/analisis-ia` (alias `/ai`)
8. Seguridad `/seguridad` (alias `/risk`)
9. Estado del sistema `/sistema` (alias `/health`)
10. Configuración `/configuracion`

## Diccionario UI (`frontend/src/ui/labels.ts`)

Backend conserva nombres técnicos. El frontend traduce: cuentas, acciones BUY/SELL/HOLD, estados FILLED/SIGNAL_ONLY, motivos de política, narrativa del bot.

## Componentes nuevos

- `layout/AppShell.tsx`
- `components/ui/MetricCard`, `StatusBadge`, `PageHeader`, `EmptyState`, `ConfirmDialog`, `ActivityFeed`
- `ui/format.ts`, `ui/labels.ts`

## Checkpoint / rollback

- Tag: `checkpoint-etapa-s-pre-20261104_092740`
- Backup DB: `backups/paper_pre_etapa_s_20261104_092740.dump`

```bash
git checkout checkpoint-etapa-s-pre-20261104_092740
docker compose up -d --build
# restaurar dump si hace falta
```

## Estado S1–S2

Completado: tokens, shell, Inicio ejecutivo, Bot Demo premium, onboarding, confirmación DETENER, posiciones básicas, títulos humanizados en páginas secundarias.

Pendiente S3–S5: terminal de mercado premium, movimientos tipo tarjeta, resultados profundos, pulido responsive/a11y integral.
