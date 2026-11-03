"""One-shot read-only audit for drawdown peak + shadow horizons + recon."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal

from app.lab.config import ACCOUNT_ID
from app.lab.valuation import fetch_marks, portfolio_valuation
from app.main import db
from app.prospect.reconcile import horizon_audit, paper_sma_integrity


async def main() -> None:
    with db() as c:
        ha = horizon_audit(c.execute)
        print("PENDING", len(ha), "any_ready", any(h["horizon_ready"] for h in ha))
        g: dict[str, list] = defaultdict(list)
        for h in ha:
            g[h["horizon_ready_after_utc"]].append(
                (h["id"], h["symbol"], h["candle_open_utc"], h["seconds_until_ready"])
            )
        for k in sorted(g):
            print("READY_AFTER", k, "n=", len(g[k]), "sample", g[k][:2])
        for h in ha:
            open_h = h["candle_open_utc"]
            if open_h.startswith("2026-11-03T18:") or open_h.startswith("2026-11-03T19:"):
                print(
                    "LOT",
                    h["id"],
                    h["symbol"],
                    "open",
                    open_h,
                    "ready",
                    h["horizon_ready_after_utc"],
                    "ready?",
                    h["horizon_ready"],
                )
        sma = paper_sma_integrity(c.execute)
        virt = c.execute(
            "SELECT cash FROM virt_accounts WHERE id='research_sim'"
        ).fetchone()
        print("SMA", sma["ok"], float(sma["cash"]), sma["positions"], sma["trades"])
        print("VIRT", float(virt["cash"]) if virt else None)

        pos = list(c.execute("SELECT * FROM lab_positions"))
        marks = await fetch_marks([p["symbol"] for p in pos])
        v = portfolio_valuation(c.execute, marks)
        cash = Decimal(str(v["cash"]))
        mv = sum(
            Decimal(str(p["qty"])) * Decimal(str(marks[p["symbol"]]["price"]))
            for p in pos
            if marks.get(p["symbol"], {}).get("ok")
        )
        cost = sum((Decimal(str(p["cost"])) for p in pos), Decimal("0"))
        print(
            "RECON",
            "cash",
            float(cash),
            "mv",
            float(mv),
            "cost",
            float(cost),
            "equity",
            float(cash + mv),
            "api",
            v["equity_estimate"],
        )
        print("unreal", float(mv - cost), "api_unreal", v["unrealized_pnl"])
        print(
            "peak_api",
            v["peak_equity"],
            "dd_api",
            v["drawdown_vs_peak"],
            "ret",
            v["return_vs_initial"],
        )
        row = c.execute(
            """SELECT MAX(start_equity) AS s, MAX(end_equity) AS e
               FROM lab_equity_daily WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()
        peak_correct = max(
            Decimal(str(row["s"] or 0)),
            Decimal(str(row["e"] or 0)),
            Decimal(str(v["initial_capital"])),
        )
        eq = Decimal(str(v["equity_estimate"]))
        dd_correct = (
            float((peak_correct - eq) / peak_correct) if eq < peak_correct else 0.0
        )
        print(
            "PEAK_CORRECT",
            float(peak_correct),
            "DD_CORRECT_FRAC",
            dd_correct,
            "DD_PCT",
            dd_correct * 100,
        )
        # Bug demonstration
        buggy = c.execute(
            """SELECT MAX(COALESCE(end_equity, start_equity)) AS peak
               FROM lab_equity_daily WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()["peak"]
        print("PEAK_BUGGY_COALESCE", float(buggy))


if __name__ == "__main__":
    asyncio.run(main())
