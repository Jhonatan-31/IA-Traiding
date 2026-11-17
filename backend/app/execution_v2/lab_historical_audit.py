"""AM8 — auditoría solo lectura de SELLs Lab potencialmente afectados por doble fee.

No muta ledgers. No crea asientos compensatorios.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable


def _d(x) -> Decimal:
    return Decimal(str(x))


def classify_sell_row(
    *,
    qty: Decimal,
    price: Decimal,
    fee: Decimal,
    fee_rate: Decimal,
    fill_price_was_all_in: bool | None,
) -> dict[str, Any]:
    """
    Si fill era all-in (V1), el cash correcto = qty*price.
    El bug restaba fee otra vez → cash acreditado ≈ qty*price - fee.

    Sin cash_before/after por trade, estimamos:
    - fee_expected_if_all_in ≈ proceeds * f/(1-f)  (reporting)
    - fee_if_gross = proceeds * f
    Clasificación heurística; muchas filas pueden ser NO_DETERMINABLE.
    """
    proceeds = qty * price
    if proceeds <= 0:
        return {
            "status": "NO_DETERMINABLE",
            "reason": "non_positive_proceeds",
        }
    fee_from_all_in = proceeds * fee_rate / (Decimal("1") - fee_rate) if fee_rate < 1 else Decimal("0")
    fee_from_gross = proceeds * fee_rate
    # Tolerances
    tol = max(Decimal("1e-8"), proceeds * Decimal("1e-9"))
    if fill_price_was_all_in is True:
        # Lab paper path uses V1 all-in prices. Pre-AL apply_sell debited fee again.
        # Without per-trade cash trail we cannot CONFIRMADO absolute; mark PROBABLE.
        if fee <= 0:
            return {
                "status": "NO_DETERMINABLE",
                "reason": "zero_fee_with_all_in_assumption",
                "estimated_cash_undercredit": 0.0,
            }
        return {
            "status": "PROBABLE",
            "reason": "all_in_v1_path_pre_al_double_debit_code",
            "proceeds_all_in": float(proceeds),
            "fee_recorded": float(fee),
            "fee_expected_reporting": float(fee_from_all_in),
            "estimated_cash_undercredit": float(fee),
            "note": "CONFIRMADO requires cash before/after audit trail — not available per row",
        }
    # Heuristic without convention flag:
    if abs(fee - fee_from_all_in) <= tol * 10 and fee > 0:
        return {
            "status": "PROBABLE",
            "reason": "fee_matches_all_in_reconstruction",
            "proceeds": float(proceeds),
            "fee_recorded": float(fee),
            "fee_expected_reporting": float(fee_from_all_in),
            "estimated_cash_undercredit": float(fee),
            "note": "Assumes pre-AL apply_sell double-debit; not proven per-row without cash trail",
        }
    if abs(fee - fee_from_gross) <= tol * 10 and fee > 0:
        return {
            "status": "PROBABLE",
            "reason": "fee_matches_gross_times_rate",
            "proceeds": float(proceeds),
            "fee_recorded": float(fee),
            "estimated_cash_undercredit": float(fee),
            "note": "If price was all-in, cash still undercredited by ~fee under old code",
        }
    if fee == 0:
        return {
            "status": "NO_DETERMINABLE",
            "reason": "zero_fee",
            "estimated_cash_undercredit": 0.0,
        }
    return {
        "status": "NO_DETERMINABLE",
        "reason": "fee_convention_ambiguous",
        "fee_recorded": float(fee),
        "fee_from_all_in": float(fee_from_all_in),
        "fee_from_gross": float(fee_from_gross),
        "estimated_cash_undercredit": None,
    }


def audit_lab_sells_readonly(
    execute: Callable,
    *,
    fee_rate: Decimal = Decimal("0.001"),
    assume_all_in_v1: bool = True,
) -> dict[str, Any]:
    """Lee lab_trades SELL; no escribe."""
    rows = list(
        execute(
            """SELECT id, account_id, at, symbol, qty, price, fee, slip, realized_pnl, reason, strategy
               FROM lab_trades WHERE side='SELL' ORDER BY id"""
        )
    )
    findings = []
    confirmed = probable = undetermined = 0
    impact_sum = Decimal("0")
    impact_n = 0
    for r in rows:
        cls = classify_sell_row(
            qty=_d(r["qty"]),
            price=_d(r["price"]),
            fee=_d(r["fee"]),
            fee_rate=fee_rate,
            fill_price_was_all_in=True if assume_all_in_v1 else None,
        )
        st = cls["status"]
        if st == "CONFIRMADO":
            confirmed += 1
        elif st == "PROBABLE":
            probable += 1
        else:
            undetermined += 1
        est = cls.get("estimated_cash_undercredit")
        if est is not None:
            impact_sum += _d(est)
            impact_n += 1
        findings.append(
            {
                "id": r["id"],
                "account_id": r["account_id"],
                "at": str(r.get("at")),
                "symbol": r["symbol"],
                **cls,
            }
        )
    accounts = sorted({str(r["account_id"]) for r in rows})
    period = None
    if rows:
        period = {"from": str(rows[0].get("at")), "to": str(rows[-1].get("at"))}
    missing_for_confirm = [
        "cash_before per trade",
        "cash_after per trade",
        "executor_code_version / deploy commit at fill time",
        "explicit fill_price_is_all_in flag persisted on row",
        "fee currency (assumed quote USDT)",
    ]
    return {
        "readonly": True,
        "mutates_ledgers": False,
        "regularization_executed": False,
        "n_sells_examined": len(rows),
        "n_confirmado": confirmed,
        "n_probable": probable,
        "n_descartado": 0,
        "n_no_determinable": undetermined,
        "accounts": accounts,
        "period": period,
        "estimated_aggregate_undercredit_usdt": float(impact_sum) if impact_n else None,
        "impact_rows_with_estimate": impact_n,
        "impact_uncertain_usdt": float(impact_sum) if impact_n else None,
        "assume_all_in_v1": assume_all_in_v1,
        "code_dependency": (
            "Pre-AL apply_sell debited fee after all-in credit when fill_price from "
            "estimate_fill_price; AL fixed forward only."
        ),
        "missing_to_upgrade_probable_to_confirmado": missing_for_confirm,
        "limitations": [
            "Sin snapshot cash por trade, el impacto es estimado",
            "No se reescriben fills ni saldos",
            "CONFIRMADO requiere trail de efectivo o flag persistido — no disponible",
        ],
        "proposed_regularization": {
            "steps": [
                "Exportar findings a CSV inmutable",
                "Revisar muestra manual de N trades",
                "Autorizar asiento compensatorio único por cuenta (no reescribir fills)",
                "Documentar hash del export y aprobación",
            ],
            "authorized_in_am": False,
            "authorized_in_an": False,
        },
        "findings_sample": findings[:20],
        "findings_count": len(findings),
    }
