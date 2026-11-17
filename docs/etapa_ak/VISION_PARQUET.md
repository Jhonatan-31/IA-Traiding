# AK — Auditoría Binance Vision / Parquet

## Pérdida actual (V1)

`parse_klines_csv` + `write_month_parquet` persisten solo:

`open_time, open, high, low, close, volume, is_closed`

Vision CSV además trae:

`close_time, quote_volume, number_of_trades, taker_buy_base, taker_buy_quote`

## Corrección no destructiva

- Parser: `execution_v2.vision_ingest.parse_klines_csv_vision`
- Escritura: `write_vision_ext_parquet` → `*_vision_ext.parquet` **sin** reemplazar OHLCV V1
- `replaces_v1_ohlcv: false` · `fabricated_bbo: false`

Re-ingesta masiva: opt-in futura; no ejecutada en AK sobre datos productivos.
