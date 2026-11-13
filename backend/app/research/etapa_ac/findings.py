"""Matriz de hallazgos AC — solo defectos/evidencias demostrables."""
from __future__ import annotations

from typing import Any

FINDINGS: list[dict[str, Any]] = [
    {
        "id": "AC-F01",
        "priority": "P0",
        "title": "Runners de protección no están en ejecución",
        "description": (
            "demo-runner, active-runner, trade-executor, worker y shadow-scheduler "
            "constan Exited (137) hace ~2 días. compose los define restart:unless-stopped, "
            "pero no están vivos. Sin runner, STOPPED no puede evaluar salidas protectoras."
        ),
        "evidence": "docker compose ps -a → Exited (137); demo_positions/active/lab=0 ahora",
        "location": "compose.yaml services demo-runner/active-runner/trade-executor",
        "impact": "Si se abrieran posiciones, SL/TP/salidas no se evaluarían",
        "severity": "Alta si hay posiciones; media ahora (0 posiciones)",
        "solution": "Política: alinear runners de protección con estado deseado; alerta si exited y posiciones>0",
        "risks": "Reiniciar runners no debe reactivar entradas (A/B STOPPED)",
        "validation": "ps + count posiciones + test_demo_stop_protections",
        "rollback": "docker compose stop <runner>",
        "fixed_in_ac": False,
        "note": "No se reinician en AC sin autorización; 0 posiciones mitiga impacto inmediato",
    },
    {
        "id": "AC-F02",
        "priority": "P1",
        "title": "Parquet histórico descarta campos Binance Vision",
        "description": (
            "parse_klines_csv solo guarda OHLCV+is_closed; Vision aporta quote_volume, "
            "number_of_trades, taker_buy_base/quote. Impacta microestructura futura."
        ),
        "evidence": "download.py parse_klines_csv; store.write_month_parquet schema",
        "location": "backend/app/research/history/download.py:64-85; store.py:39-48",
        "impact": "AA8/microestructura no pueden usar taker buy sin re-parse de ZIP raw",
        "solution": "Migración no destructiva: enriquecer Parquet desde ZIP raw preservando OHLCV",
        "risks": "Cambio de schema; no alterar evals Z/AA/AB congeladas",
        "validation": "test_vision_fields_dropped + roundtrip sample",
        "rollback": "mantener columnas nuevas opcionales",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F03",
        "priority": "P1",
        "title": "Simulador research usa close + fricción proxy, sin BBO",
        "description": (
            "Motor Z/AA/AB ejecuta al close con fee+slip+spread_bps/20000. "
            "No bid/ask histórico. Costos D28H5 72.73 pueden ser optimistas o pesimistas."
        ),
        "evidence": "etapa_z/engine.py _trade_cost; etapa_ab/simulate_ledger COST_FRAC",
        "location": "backend/app/research/etapa_z/engine.py; etapa_ab/simulate_ledger.py",
        "impact": "Confianza limitada en P/L neto y en +90.75 vs FIXED-55",
        "solution": "Modelo de ejecución versionado separado; no reescribir informes históricos",
        "risks": "Comparabilidad con Z/AA/AB",
        "validation": "suite sensibilidad costos ya en AA; ampliar con spread×2/×3 en AC docs",
        "rollback": "N/A documental",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F04",
        "priority": "P1",
        "title": "Host personal: sin detector de suspensión/huecos operativos unificado",
        "description": (
            "Documentado hueco previo por suspensión Windows. No hay SLI de "
            "'host_suspend_gap' correlacionando runners+market-stream+DB."
        ),
        "evidence": "brief AC + runners Exited 137 típico de kill/restart Docker Desktop",
        "location": "ops/local; main.py heartbeat shadow parcial",
        "impact": "Ciclos omitidos sin alerta agregada",
        "solution": "Métrica gap = now - max(heartbeats); dashboard CRÍTICO si gap>N",
        "risks": "Falsos positivos en idle STOPPED",
        "validation": "inyectar heartbeat viejo en test",
        "rollback": "feature flag",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F05",
        "priority": "P1",
        "title": "D28H5: costos de rotación elevados vs beneficio relativo",
        "description": (
            "72.733833 USDT en fricciones; 189 rebalances_real; 356 turnover_events "
            "(ajustes ≥1 USDT/símbolo, no round-trips). ~7.3% del capital."
        ),
        "evidence": "etapa_ab_results costs_audit + reconcile_ab",
        "location": "docs/etapa_ab; research/etapa_ab",
        "impact": "Erosiona ventaja vs FIXED-55; stress de costos en AA ya negativo",
        "solution": "Hipótesis AB-H3 bandas (registrada, no ejecutar en holdout)",
        "risks": "Optimizar en AA sería leakage",
        "validation": "descriptivo only",
        "rollback": "N/A",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F06",
        "priority": "P2",
        "title": "AB-PROSPECT-v1 preparado pero sin almacenamiento/job implementado",
        "description": (
            "prospect.py define protocolo y OBSERVATION_ENABLED=False; no hay writer "
            "de decisions.jsonl ni runner de observación."
        ),
        "evidence": "etapa_ab/prospect.py OBSERVATION_ENABLED=False; decisions_recorded=0",
        "location": "backend/app/research/etapa_ab/prospect.py",
        "impact": "No listo para activación sin trabajo adicional de ingeniería",
        "solution": "Implementar store+job aislado antes de pedir autorización",
        "risks": "Activar prematuro → señales incompletas",
        "validation": "tests inmutabilidad cuando exista writer",
        "rollback": "mantener disabled",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F07",
        "priority": "P2",
        "title": "Observabilidad fragmentada",
        "description": (
            "Existen heartbeats por runner y freshness market-stream, pero no un "
            "panel único de auditoría profesional con severidades INFO/WARN/CRIT."
        ),
        "evidence": "main.py shadow heartbeat; market_stream hub.freshness; UI parcial",
        "location": "backend/app/main.py; market_stream/hub.py",
        "impact": "Operador puede ver dashboard 'vivo' con runners muertos",
        "solution": "Panel Auditoría profesional AC (implementar lectura)",
        "risks": "bajo",
        "validation": "API status refleje exited runners",
        "rollback": "UI only",
        "fixed_in_ac": True,
        "note": "Panel de lectura en dashboard AC",
    },
    {
        "id": "AC-F08",
        "priority": "P2",
        "title": "min_hold=5 en meta D28H5 no aplicado en código",
        "description": "Documentado en AA/AB; riesgo de malinterpretar el nombre D28H5.",
        "evidence": "freeze.executable_behavior min_hold_in_code=False",
        "location": "etapa_z/hypotheses.py; etapa_aa/freeze.py",
        "impact": "Confusión de investigación; no bug de ledger",
        "solution": "Mantener disclaimer en UI/docs (ya en AA)",
        "risks": "ninguno si no se 'arregla' la estrategia congelada",
        "validation": "freeze hash",
        "rollback": "N/A",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F09",
        "priority": "P2",
        "title": "Ventaja D28H5 vs FIXED-55 no validada estadísticamente fuera de AA",
        "description": (
            "+90.7526 USDT vs FIXED-55 en holdout consumido; IC bootstrap AA del exceso "
            "vs BH-EQ incluía cero; P/L absoluto negativo."
        ),
        "evidence": "reconcile_ab + AA stats",
        "location": "etapa_ab/etapa_aa artifacts",
        "impact": "No autoriza PAPER ni real",
        "solution": "Solo revisión futura de observación tras P0/P1",
        "risks": "sobreinterpretación",
        "validation": "veredicto económico AC",
        "rollback": "N/A",
        "fixed_in_ac": False,
    },
    {
        "id": "AC-F10",
        "priority": "P3",
        "title": "db Postgres no expuesto a host; dashboard solo 127.0.0.1",
        "description": "Buen default de red; LAB_CONTROL_TOKEN requerido en compose.",
        "evidence": "compose.yaml ports 127.0.0.1:8088; LAB_CONTROL_TOKEN required",
        "location": "compose.yaml",
        "impact": "positivo — menor superficie",
        "solution": "mantener; auditar logs por secretos en siguientes etapas",
        "risks": "ninguno",
        "validation": "inspección compose",
        "rollback": "N/A",
        "fixed_in_ac": False,
        "is_strength": True,
    },
    {
        "id": "AC-F11",
        "priority": "P0",
        "title": "Compra sin rollback si falla creación de posición",
        "description": (
            "demo/active: cash se debita y luego INSERT posición ON CONFLICT DO NOTHING; "
            "si no hay fila, retorna position_not_created sin devolver el cash."
        ),
        "evidence": "demo/engine.py ~418-427; active/engine.py pattern equivalente",
        "location": "backend/app/demo/engine.py; backend/app/active/engine.py",
        "impact": "Corrupción contable: cash↓ sin inventario",
        "severity": "Baja en operación normal; alta si carrera/duplicado de símbolo",
        "solution": "Transacción única + rollback cash o DELETE orden/refund",
        "risks": "Tocar ledgers demo/active — requiere etapa dedicada y tests",
        "validation": "test integración compra duplicada → cash invariante",
        "rollback": "revertir fix; no alterar historial a mano",
        "fixed_in_ac": False,
        "source": "auditoría explore riesgo/ledgers",
    },
    {
        "id": "AC-F12",
        "priority": "P0",
        "title": "Active B omite salidas protectoras si ejecución no autorizada",
        "description": (
            "Si B_EXECUTION_AUTHORIZED=False, run_cycle retorna antes de evaluar "
            "posiciones/SL-TP. Distinto de STOPPED (que sí permite salidas)."
        ),
        "evidence": "active/engine.py L113-116 early return",
        "location": "backend/app/active/engine.py",
        "impact": "Posiciones B quedarían sin protección bajo flag False",
        "severity": "Baja hoy (flag=True en __init__); crítica si se desautoriza B",
        "solution": "Evaluar salidas protectoras antes del gate de autorización de entradas",
        "risks": "Cambio semántico de B — etapa controlada",
        "validation": "test: flag False + posición abierta ⇒ SELL protector permitido",
        "rollback": "revertir motor B",
        "fixed_in_ac": False,
        "source": "auditoría explore riesgo/ledgers",
    },
    {
        "id": "AC-F13",
        "priority": "P1",
        "title": "Doble cargo de fee en cash demo/active/express",
        "description": (
            "estimate_fill_price ya incorpora fee_rate en px; luego total=qty*px+fee "
            "vuelve a sumar fee al debitar cash."
        ),
        "evidence": "prospect/execution.py estimate_fill_price; demo/engine total=qty*px+fee",
        "location": "backend/app/demo/engine.py; active/engine.py; express/engine.py",
        "impact": "Costos PAPER sobreestimados; distorsiona auditoría económica operativa",
        "solution": "Unificar: fee solo en px O solo como add-on, no ambos",
        "risks": "Cambiar PnL histórico simulado de A/B",
        "validation": "caso unitario qty/px/fee → cash delta exacto",
        "rollback": "revertir; no reescribir trades viejos sin migración",
        "fixed_in_ac": False,
        "source": "auditoría explore riesgo/ledgers",
    },
    {
        "id": "AC-F14",
        "priority": "P1",
        "title": "Dedupe trade_id market-stream puede fallar bajo alto throughput",
        "description": (
            "Al superar _MAX_SEEN_IDS=4096 se recorta seen_ids; un trade_id ya visto "
            "puede reaplicarse e inflar volumen de vela."
        ),
        "evidence": "market_stream/aggregator.py eviction half-set",
        "location": "backend/app/market_stream/aggregator.py",
        "impact": "Velas viz/agregadas con volumen inflado (no órdenes)",
        "solution": "Estructura LRU/bloom o ventana por open_time; test >4096 trades",
        "risks": "Memoria",
        "validation": "test eviction + replay trade_id",
        "rollback": "revert aggregator",
        "fixed_in_ac": False,
        "source": "auditoría explore market-stream",
    },
    {
        "id": "AC-F15",
        "priority": "P2",
        "title": "Express API sin LAB_CONTROL_TOKEN",
        "description": "lab/demo/active usan require_lab_token; express/api no.",
        "evidence": "compose LAB_CONTROL_TOKEN; express/api.py sin require_lab_token",
        "location": "backend/app/express/api.py",
        "impact": "Superficie de control desigual (express ENDED actualmente)",
        "solution": "Alinear auth o documentar excepción consciente",
        "risks": "bajo si express sigue ENDED",
        "validation": "401 sin token en mutaciones express",
        "rollback": "N/A",
        "fixed_in_ac": False,
        "source": "auditoría explore inventario",
    },
]


def findings_summary() -> dict[str, Any]:
    by_p: dict[str, int] = {}
    for f in FINDINGS:
        by_p[f["priority"]] = by_p.get(f["priority"], 0) + 1
    # Top: P0 primero, luego P1…
    ordered = sorted(
        FINDINGS,
        key=lambda f: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(f["priority"], 9), f["id"]),
    )
    return {
        "n": len(FINDINGS),
        "by_priority": by_p,
        "items": FINDINGS,
        "top10": ordered[:10],
    }
