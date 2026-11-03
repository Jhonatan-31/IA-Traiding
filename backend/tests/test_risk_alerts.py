from decimal import Decimal

from app.alerts import evaluate_alerts
from app.risk import build_risk_report, equity_drawdown, realized_pnl_and_fees


class FakeConn:
    def __init__(self):
        self.tables = {}
        self.alerts = []
        self.limits = {
            "id": 1,
            "max_daily_loss_pct": 5,
            "max_drawdown_pct": 15,
            "max_exposure_pct": 80,
            "max_positions": 10,
            "max_trades_per_day": 50,
            "stale_data_seconds": 7200,
        }
        self._id = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        params = params or ()

        class R:
            def __init__(self, rows):
                self._rows = rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

            def __iter__(self):
                return iter(self._rows)

        if s.startswith("create") or s.startswith("insert into risk_limits"):
            return R([])
        if "from risk_limits" in s:
            return R([self.limits])
        if s.startswith("select id from alerts where fingerprint"):
            fp = params[0]
            rows = [a for a in self.alerts if a["fingerprint"] == fp and a["status"] == "OPEN"]
            return R(rows)
        if s.startswith("update alerts set updated_at"):
            for a in self.alerts:
                if a["id"] == params[3]:
                    a["detail"] = params[0]
                    a["severity"] = params[1]
                    a["title"] = params[2]
            return R([])
        if s.startswith("insert into alerts"):
            row = {
                "id": self._id,
                "severity": params[0],
                "code": params[1],
                "title": params[2],
                "detail": params[3],
                "status": "OPEN",
                "fingerprint": params[4],
            }
            self._id += 1
            self.alerts.append(row)
            return R([])
        if "set status='resolved'" in s or 'set status="resolved"' in s or "status='resolved'" in s:
            fp = params[0]
            for a in self.alerts:
                if a["fingerprint"] == fp and a["status"] == "OPEN":
                    a["status"] = "RESOLVED"
            return R([])
        if "count(*) as n from alerts where status='open'" in s:
            n = len([a for a in self.alerts if a["status"] == "OPEN"])
            return R([{"n": n}])
        if s.startswith("select * from alerts"):
            return R(list(self.alerts))
        return R([])


def test_realized_pnl_fifo():
    trades = [
        {"id": 1, "symbol": "AAA", "side": "BUY", "qty": 2, "price": 10, "fee_rate": 0},
        {"id": 2, "symbol": "AAA", "side": "SELL", "qty": 2, "price": 12, "fee_rate": 0},
    ]
    pack = realized_pnl_and_fees(trades)
    assert pack["realized_pnl"] == Decimal("4")


def test_drawdown_exact():
    dd = equity_drawdown([100, 110, 90, 95])
    assert abs(dd["max_drawdown_pct"] - ((90 - 110) / 110 * 100)) < 1e-9
    assert dd["points"] == 4


def test_risk_report_accounting_and_limits():
    report = build_risk_report(
        cash=Decimal("925"),
        positions=[
            {
                "symbol": "ETHUSDT",
                "qty": Decimal("0.01"),
                "cost": Decimal("25"),
                "price": Decimal("2500"),
                "price_source": "live_ticker",
            }
        ],
        trades=[
            {
                "id": 1,
                "symbol": "ETHUSDT",
                "side": "BUY",
                "qty": Decimal("0.01"),
                "price": Decimal("2500"),
                "fee_rate": Decimal("0.001"),
            }
        ],
        scans=[{"equity": 1000}, {"equity": 990}],
        initial_capital=Decimal("1000"),
        limits={
            "max_exposure_pct": 1,
            "max_drawdown_pct": 0.5,
            "max_daily_loss_pct": 0.5,
            "max_positions": 10,
            "max_trades_per_day": 50,
        },
    )
    assert report["cash"] == 925
    assert "exposure_limit" in report["breaches"]
    assert report["classification"]["cash"] == "confirmed_ledger"


def test_alerts_dedup_and_resolve():
    store = FakeConn()

    def factory():
        return store

    risk = {"breaches": ["exposure_limit"], "cash": 500, "invested_cost": 500, "initial_capital": 1000, "realized_pnl": 0}
    system = {
        "db": "ok",
        "binance": {"status": "ok"},
        "last_scan": {"at": "2026-11-03T16:00:00+00:00", "errors": 0},
        "prices_max_at": "2026-11-03T16:00:00+00:00",
        "scan_every_seconds": 3600,
    }
    evaluate_alerts(factory, risk, system)
    evaluate_alerts(factory, risk, system)
    open1 = [a for a in store.alerts if a["status"] == "OPEN" and a["code"] == "EXPOSURE_LIMIT"]
    assert len(open1) == 1

    risk2 = {**risk, "breaches": []}
    evaluate_alerts(factory, risk2, system)
    open2 = [a for a in store.alerts if a["status"] == "OPEN" and a["code"] == "EXPOSURE_LIMIT"]
    assert len(open2) == 0
