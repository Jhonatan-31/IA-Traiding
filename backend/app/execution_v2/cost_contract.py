"""AN1 — Contrato económico versionado (Decimal). Sin doble fee/spread.

CONTRACT_ID = cost_contract_v1
fill_price_is_all_in: precio unitario ya neto de fee (BUY: pagas más; SELL: recibes menos).
Cash BUY = qty * price_all_in (salida). Cash SELL = qty * price_all_in (entrada).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Literal

CONTRACT_ID = "cost_contract_v1"
CONTRACT_VERSION = "1.0.0"


def D(x: Any) -> Decimal:
    return Decimal(str(x))


def q8(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)


Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class CostComponents:
    """Desglose — cada componente una sola vez."""

    ref_mid: Decimal
    bid: Decimal | None
    ask: Decimal | None
    half_spread_obs: Decimal  # (ask-bid)/2 or 0 if unknown
    mid_to_touch: Decimal  # BUY: ask-mid; SELL: mid-bid (observed) or proxy
    mid_to_touch_source: str  # observed_bbo | proxy_bps | none
    extra_slip: Decimal  # absolute per unit
    extra_slip_source: str  # assumed | none
    fee_per_unit: Decimal
    fee_source: str  # embedded_all_in
    raw_before_fee: Decimal
    price_all_in: Decimal
    qty: Decimal
    cash_total: Decimal  # BUY outlay positive; SELL credit positive
    partial: bool
    incomplete_without_l2: bool
    notes: tuple[str, ...]


def half_spread_from_bbo(bid: Decimal, ask: Decimal) -> Decimal:
    return (ask - bid) / D(2)


def buy_all_in(
    *,
    mid: Decimal,
    ask: Decimal | None,
    qty: Decimal,
    fee_rate: Decimal,
    extra_slip_rate: Decimal,
    use_observed_ask: bool,
    proxy_half_spread: Decimal = D(0),
) -> CostComponents:
    """
    BUY:
      touch = ask if use_observed_ask else mid + proxy_half_spread
      raw = touch * (1 + extra_slip_rate)
      all_in = raw * (1 + fee_rate)
      cash = qty * all_in
    Mid→ask already IS half-spread vs mid — do NOT add proxy_half_spread on top of ask.
    """
    notes: list[str] = []
    if use_observed_ask:
        if ask is None or ask <= 0:
            raise ValueError("ask_required")
        touch = ask
        mid_to_touch = ask - mid
        src = "observed_bbo"
        notes.append("spread_embodied_in_ask_not_added_again")
    else:
        touch = mid + proxy_half_spread
        mid_to_touch = proxy_half_spread
        src = "proxy_bps"
        notes.append("proxy_half_spread_assumed")
    slip_abs = touch * extra_slip_rate
    raw = touch + slip_abs  # equivalent to touch*(1+rate)
    fee = raw * fee_rate
    all_in = raw + fee  # raw*(1+fee)
    cash = qty * all_in
    return CostComponents(
        ref_mid=q8(mid),
        bid=None,
        ask=q8(ask) if ask is not None else None,
        half_spread_obs=q8(D(0)),
        mid_to_touch=q8(mid_to_touch),
        mid_to_touch_source=src,
        extra_slip=q8(slip_abs),
        extra_slip_source="assumed" if extra_slip_rate > 0 else "none",
        fee_per_unit=q8(fee),
        fee_source="embedded_all_in",
        raw_before_fee=q8(raw),
        price_all_in=q8(all_in),
        qty=q8(qty),
        cash_total=q8(cash),
        partial=False,
        incomplete_without_l2=False,
        notes=tuple(notes),
    )


def sell_all_in(
    *,
    mid: Decimal,
    bid: Decimal | None,
    qty: Decimal,
    fee_rate: Decimal,
    extra_slip_rate: Decimal,
    use_observed_bid: bool,
    proxy_half_spread: Decimal = D(0),
) -> CostComponents:
    """
    SELL:
      touch = bid if use_observed_bid else mid - proxy_half_spread
      raw = touch * (1 - extra_slip_rate)
      all_in = raw * (1 - fee_rate)
      cash = qty * all_in  (credit; fee already in all_in — do NOT debit fee again)
    """
    notes: list[str] = ["fill_price_is_all_in=True_cash_equals_qty_times_all_in"]
    if use_observed_bid:
        if bid is None or bid <= 0:
            raise ValueError("bid_required")
        touch = bid
        mid_to_touch = mid - bid
        src = "observed_bbo"
        notes.append("spread_embodied_in_bid_not_added_again")
    else:
        touch = mid - proxy_half_spread
        mid_to_touch = proxy_half_spread
        src = "proxy_bps"
        notes.append("proxy_half_spread_assumed")
    slip_abs = touch * extra_slip_rate
    raw = touch - slip_abs
    fee = raw * fee_rate
    all_in = raw - fee
    cash = qty * all_in
    return CostComponents(
        ref_mid=q8(mid),
        bid=q8(bid) if bid is not None else None,
        ask=None,
        half_spread_obs=q8(D(0)),
        mid_to_touch=q8(mid_to_touch),
        mid_to_touch_source=src,
        extra_slip=q8(slip_abs),
        extra_slip_source="assumed" if extra_slip_rate > 0 else "none",
        fee_per_unit=q8(fee),
        fee_source="embedded_all_in",
        raw_before_fee=q8(raw),
        price_all_in=q8(all_in),
        qty=q8(qty),
        cash_total=q8(cash),
        partial=False,
        incomplete_without_l2=False,
        notes=tuple(notes),
    )


def bps(diff: Decimal, ref: Decimal) -> Decimal | None:
    if ref == 0:
        return None
    return q8((diff / ref) * D(10000))


def components_to_dict(c: CostComponents) -> dict[str, Any]:
    d = asdict(c)
    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, tuple):
            d[k] = list(v)
    d["contract_id"] = CONTRACT_ID
    d["contract_version"] = CONTRACT_VERSION
    return d


def reconcile_buy_cash(mid: float, ask: float, qty: float, fee: float, slip: float) -> dict[str, Any]:
    c = buy_all_in(
        mid=D(mid),
        ask=D(ask),
        qty=D(qty),
        fee_rate=D(fee),
        extra_slip_rate=D(slip),
        use_observed_ask=True,
    )
    # Independent check
    touch = D(ask)
    raw = touch * (D(1) + D(slip))
    all_in = raw * (D(1) + D(fee))
    cash = D(qty) * all_in
    ok = abs(c.cash_total - cash) < D("1e-10")
    return {"ok": ok, "contract_cash": float(c.cash_total), "check_cash": float(cash)}


def reconcile_sell_cash(mid: float, bid: float, qty: float, fee: float, slip: float) -> dict[str, Any]:
    c = sell_all_in(
        mid=D(mid),
        bid=D(bid),
        qty=D(qty),
        fee_rate=D(fee),
        extra_slip_rate=D(slip),
        use_observed_bid=True,
    )
    touch = D(bid)
    raw = touch * (D(1) - D(slip))
    all_in = raw * (D(1) - D(fee))
    cash = D(qty) * all_in
    ok = abs(c.cash_total - cash) < D("1e-10")
    return {"ok": ok, "contract_cash": float(c.cash_total), "check_cash": float(cash)}


CONTRACT_SPEC = {
    "id": CONTRACT_ID,
    "version": CONTRACT_VERSION,
    "rules": [
        "Never double-count mid→touch spread when using ask/bid",
        "Never debit fee from cash if price_all_in already embeds fee",
        "extra_slip is assumed unless measured",
        "Without L2, size>top_qty ⇒ incomplete/partial — not full fill at touch",
        "Unit price ≠ cash notional; always report both",
    ],
    "fill_price_is_all_in": {
        "BUY": "price includes fee uplift; cash_out = qty * price",
        "SELL": "price is net of fee; cash_in = qty * price (no second fee debit)",
    },
    "legacy_defaults_note": {
        "v1": "fee=0.001, base_slip=0.001, spread_bps=2",
        "v2": "fee=0.001, extra_slip=0.0002",
    },
}
