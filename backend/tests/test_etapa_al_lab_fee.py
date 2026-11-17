"""AL1 — forense Lab SELL: no descontar fee dos veces cuando fill_price es all-in."""
from __future__ import annotations

from decimal import Decimal

from app.lab.config import FEE_RATE
from app.lab.ledger import apply_buy, apply_sell
from app.prospect.execution import ExecutionAssumptions, estimate_fill_price


class _FakeDB:
    """Ledger aislado en memoria (sin Postgres productivo)."""

    def __init__(self, cash: float = 1000.0):
        self.cash = Decimal(str(cash))
        self.initial = Decimal(str(cash))
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []

    def execute(self, sql: str, params=None):
        s = " ".join(sql.split()).upper()
        params = params or ()

        class R:
            def __init__(self, row=None, rows=None):
                self._row = row
                self._rows = rows or ([] if row is None else [row])

            def fetchone(self):
                return self._row

            def __iter__(self):
                return iter(self._rows)

        if "SELECT CASH FROM LAB_ACCOUNTS" in s:
            return R({"cash": self.cash})
        if "SELECT * FROM LAB_ACCOUNTS" in s:
            return R({"id": 1, "cash": self.cash, "initial_capital": self.initial})
        if "UPDATE LAB_ACCOUNTS SET CASH" in s:
            self.cash = Decimal(str(params[0]))
            return R()
        if "SELECT * FROM LAB_POSITIONS" in s and "AND SYMBOL" in s:
            sym = params[1]
            return R(self.positions.get(sym))
        if "SELECT * FROM LAB_POSITIONS" in s:
            return R(None, list(self.positions.values()))
        if "INSERT INTO LAB_POSITIONS" in s:
            self.positions[params[1]] = {
                "account_id": params[0],
                "symbol": params[1],
                "qty": Decimal(str(params[2])),
                "cost": Decimal(str(params[3])),
                "entry_price": Decimal(str(params[4])),
            }
            return R()
        if "DELETE FROM LAB_POSITIONS" in s:
            self.positions.pop(params[1], None)
            return R()
        if "INSERT INTO LAB_TRADES" in s:
            self.trades.append({"sql": sql, "params": params})
            return R()
        return R()


def test_al_lab_sell_no_double_fee_all_in_price():
    """
    V1 SELL fill_price ya es neto de fee.
    Cash debe recibir qty*fill_price SIN restar fee otra vez.
    """
    db = _FakeDB(1000.0)
    mid = 100.0
    assumptions = ExecutionAssumptions(
        fee_rate=float(FEE_RATE), base_slip_rate=0.0, spread_bps=0.0
    )
    buy_fill = estimate_fill_price(side="BUY", mid_or_ref=mid, assumptions=assumptions)
    assert buy_fill["ok"]
    budget = Decimal("100")
    buy = apply_buy(
        db.execute,
        order_uid="00000000-0000-0000-0000-000000000001",
        symbol="BTCUSDT",
        budget=budget,
        fill_price=Decimal(str(buy_fill["price"])),
        candle_ms=1,
        strategy="test",
        reason="test_buy",
    )
    assert buy["status"] == "FILLED"
    cash_after_buy = db.cash

    sell_fill = estimate_fill_price(side="SELL", mid_or_ref=mid, assumptions=assumptions)
    assert sell_fill["ok"]
    px = Decimal(str(sell_fill["price"]))
    qty = db.positions["BTCUSDT"]["qty"]
    expected_credit = qty * px  # all-in net; NO second fee debit

    sell = apply_sell(
        db.execute,
        order_uid="00000000-0000-0000-0000-000000000002",
        symbol="BTCUSDT",
        fill_price=px,
        candle_ms=2,
        strategy="test",
        reason="test_sell",
    )
    assert sell["status"] == "FILLED"
    # Wrong (double fee) would be: cash_after_buy + expected_credit * (1 - FEE_RATE)
    assert abs(float(db.cash - (cash_after_buy + expected_credit))) < 1e-9
    # Round-trip with zero slip/spread should not lose ~fee twice
    loss = float(db.initial - db.cash)
    # One round-trip fee drag is expected (~2 * fee on notionals), not ~3-4x
    assert loss < float(budget) * float(FEE_RATE) * 3.5


def test_al_lab_sell_fee_zero_path():
    db = _FakeDB(500.0)
    apply_buy(
        db.execute,
        order_uid="00000000-0000-0000-0000-000000000011",
        symbol="ETHUSDT",
        budget=Decimal("50"),
        fill_price=Decimal("10"),
        candle_ms=1,
        strategy="t",
        reason="b",
        fee=Decimal("0"),
    )
    # Manual position with fill already net
    sell = apply_sell(
        db.execute,
        order_uid="00000000-0000-0000-0000-000000000012",
        symbol="ETHUSDT",
        fill_price=Decimal("10"),
        candle_ms=2,
        strategy="t",
        reason="s",
        fee=Decimal("0"),
    )
    assert sell["status"] == "FILLED"
    assert sell["fee"] == 0.0
