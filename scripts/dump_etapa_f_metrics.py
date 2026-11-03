import json
import urllib.request

base = "http://127.0.0.1:8088"


def get(path: str):
    with urllib.request.urlopen(base + path) as r:
        return json.load(r)


d = get("/api/ml/comparison")
print("=== AUC ===")
print(
    "hgb",
    d.get("mean_roc_auc_hist_gb"),
    "naive",
    d.get("mean_roc_auc_naive"),
    "ci",
    d.get("roc_auc_ci"),
    "ece",
    d.get("mean_ece_calibrated_test"),
)
print("\n=== STRATEGY COMPARISON ===")
for r in d.get("strategy_comparison") or []:
    ci = r.get("net_return_ci") or {}
    print(
        f"{r['strategy']:22} net={r.get('mean_net_return_sum')} "
        f"ci=({ci.get('low')},{ci.get('high')}) "
        f"trades={r.get('mean_trades')} dd={r.get('mean_max_drawdown')} "
        f"pf={r.get('mean_profit_factor')} robust={r.get('robust_edge')}"
    )
print("\n=== CALIBRATION FOLDS ===")
cal = d.get("calibration") or {}
for i, f in enumerate(cal.get("folds") or []):
    t = f.get("test_after_selection") or {}
    print(
        f"fold{i} selected={f.get('selected')} "
        f"brier={t.get('brier')} ece={t.get('ece')} logloss={t.get('log_loss')}"
    )
fh = cal.get("final_holdout") or {}
if fh:
    print("final_holdout raw", {k: fh.get("test_raw", {}).get(k) for k in ("brier", "ece", "log_loss")})
    print(
        "final_holdout cal",
        {k: fh.get("test_calibrated", {}).get(k) for k in ("brier", "ece", "log_loss")},
    )

print("\n=== PRED SUMMARY ===")
print(json.dumps(get("/api/ml/predictions/summary"), indent=2))
print("\n=== RESOLVED SAMPLE ===")
rows = get("/api/ml/predictions?resolved_only=true&limit=20")
for r in rows:
    print(
        r["symbol"],
        r.get("source"),
        round(r["probability"], 4),
        "y",
        r.get("observed_label"),
        "net",
        None if r.get("observed_net_return") is None else round(r["observed_net_return"], 5),
    )
