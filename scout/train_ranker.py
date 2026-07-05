"""
scout/train_ranker.py — daily training + champion/challenger evaluation (cloud or local).

Runs in GitHub Actions (.github/workflows/train-ranker.yml, 08:17 UTC daily) and locally. One
cycle: pull training rows from Supabase (all tiers, labels.py) -> train the CHALLENGER (the
classical model: class-balanced logistic regression until V3's LightGBM ranker lands) -> compare
it against the CHAMPION (the deterministic triage formula, scoring.triage_score) on a held-out
BY-ASIN split -> append learning-hub/tracking/ranker-report.md -> upload the model artifact +
report to the Supabase storage bucket `models/` (ranker/<date>/ + a stable ranker/current/) ->
post a summary to the brain-proposals Discord stream.

NON-NEGOTIABLES (test-enforced by tests/test_train_ranker.py):
  * NO AUTOMATIC PROMOTION, regardless of where training ran: this script NEVER writes
    ai-brain.json. Promotion happens only when Mehmet flips the brain key
    scoring.rankingChampion via fba-brain-updater; until then the trained model is shadow-only.
  * Refuses honestly below the data floor (brain learning.minLabeledRows, both classes present)
    — a refusal exits 0 with a "not enough data" report, never a fabricated metric.
  * Tier honesty: metrics are reported per label_quality tier; backtest rows are the weakest
    tier and the report says so every time.

Local side: run_daily calls fetch_current_model() at cycle start (best-effort) so the local
pipeline always has the latest cloud-trained champion candidate on disk for shadow use.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "ranker-report.md")
MODELS_DIR = os.path.join(HERE, "..", "learning-hub", "models", "ranker")
BUCKET = "models"

# Numeric subset of db.PRE_DECISION_FEATURES — the ONLY model inputs (leakage contract).
NUMERIC_FEATURES = ("price", "weight_lb", "sales_rank", "est_sales", "offers",
                    "avg_price_90", "avg_offers_90", "avg_sales_rank_90", "oos_90",
                    "amazon_bb_share")


# --- dataset -----------------------------------------------------------------
def build_dataset() -> Dict[str, Any]:
    """Training rows from Supabase via labels.py (gold + silver + backtest — the ranker is the
    one consumer that opts backtest in, per DATA_ENGINE_PLAN.md V2/V3)."""
    import labels
    assembled = labels.assemble_training_rows(include_silver=True, include_backtest=True)
    return assembled


def build_matrix(rows: List[Dict[str, Any]]) -> Tuple[Any, Any]:
    """Rows -> (X, y) over NUMERIC_FEATURES only. None -> 0.0 (explicit, same as the
    calibration diagnostic)."""
    import numpy as np
    X = np.array([[float((r.get("features") or {}).get(k) or 0.0) for k in NUMERIC_FEATURES]
                  for r in rows])
    y = np.array([1 if r["label"] else 0 for r in rows])
    return X, y


def champion_scores(rows: List[Dict[str, Any]]) -> List[Optional[float]]:
    """The CHAMPION: the deterministic triage formula, computed from the same pre-decision
    features. None (can't rank) sorts to the bottom, matching pipeline behavior."""
    import scoring
    out = []
    for r in rows:
        f = r.get("features") or {}
        out.append(scoring.triage_score(
            {"price": f.get("price"), "est_sales": f.get("est_sales"),
             "weight_lb": f.get("weight_lb")}, category=f.get("category")))
    return out


# --- evaluation ---------------------------------------------------------------
def rank_metrics(scores: List[Optional[float]], y: List[int], top_n: int = 10) -> Dict[str, Any]:
    """AUC + winners-in-top-N for one scorer. None scores rank last. AUC is None when only one
    class is present (never fabricated)."""
    import numpy as np
    from sklearn.metrics import roc_auc_score
    s = np.array([(-1e18 if v is None else float(v)) for v in scores])
    y = np.array(y)
    auc = float(roc_auc_score(y, s)) if len(set(y.tolist())) > 1 else None
    order = np.argsort(-s)
    top = order[:top_n]
    return {"auc": auc, "winners_in_top": int(y[top].sum()), "top_n": min(top_n, len(y))}


def verdict_line(champ: Dict[str, Any], chall: Dict[str, Any], margin: float = 0.02) -> str:
    """The explicit champion/challenger verdict (V3 spec wording). The challenger must BEAT the
    champion's AUC by `margin` to even claim a win — and a win still only REQUESTS promotion."""
    ca, xa = champ.get("auc"), chall.get("auc")
    if ca is None or xa is None:
        return "VERDICT: INCONCLUSIVE (single-class validation slice) — challenger stays shadow."
    if xa > ca + margin:
        return ("VERDICT: CHALLENGER WINS on held-out AUC — promotion requires human approval "
                "(flip scoring.rankingChampion via fba-brain-updater; nothing was auto-applied).")
    return "VERDICT: CHALLENGER LOSES — stays shadow."


def train_and_evaluate(assembled: Dict[str, Any]) -> Dict[str, Any]:
    """The full training cycle on already-pulled rows. Pure of I/O to Supabase/Discord — callable
    from tests with synthetic rows."""
    import backtest  # split_by_asin — the same leakage-safe splitter V2 tests enforce
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    rows = assembled["rows"]
    if assembled.get("refused"):
        return {"refused": True, "reason": assembled["reason"], "by_tier": assembled.get("by_tier", {})}

    train, val = backtest.split_by_asin(rows, val_fraction=0.3)
    if not train or not val:
        return {"refused": True, "reason": "by-ASIN split left an empty side", "by_tier": assembled.get("by_tier", {})}
    Xtr, ytr = build_matrix(train)
    Xva, yva = build_matrix(val)
    if len(set(ytr.tolist())) < 2:
        return {"refused": True, "reason": "training side has one class after the by-ASIN split",
                "by_tier": assembled.get("by_tier", {})}

    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(scaler.transform(Xtr), ytr)
    proba = clf.predict_proba(scaler.transform(Xva))[:, 1]

    chall = rank_metrics([float(p) for p in proba], yva.tolist())
    champ = rank_metrics(champion_scores(val), yva.tolist())
    return {
        "refused": False,
        "model": clf, "scaler": scaler, "features": list(NUMERIC_FEATURES),
        "train_rows": len(train), "val_rows": len(val),
        "train_asins": len({r["asin"] for r in train if r.get("asin")}),
        "val_asins": len({r["asin"] for r in val if r.get("asin")}),
        "by_tier": assembled.get("by_tier", {}),
        "champion": champ, "challenger": chall,
        "verdict": verdict_line(champ, chall),
        "silver_caveat": assembled.get("silver_caveat", ""),
    }


# --- report -------------------------------------------------------------------
def render_report(result: Dict[str, Any]) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## {now} — ranker training + champion/challenger", ""]
    tiers = result.get("by_tier") or {}
    if tiers:
        tier_bits = [f"{t}: {c['total']} ({c['positive']} pos/{c['negative']} neg)"
                     for t, c in sorted(tiers.items())]
        lines.append("- Label tiers: " + "; ".join(tier_bits))
    if result.get("refused"):
        lines += ["", f"**REFUSED to train:** {result['reason']}.",
                  "No model was fit; nothing was uploaded or promoted.", ""]
        return "\n".join(lines)
    ch, xl = result["champion"], result["challenger"]
    lines += [
        f"- Split BY ASIN: train {result['train_rows']} rows / {result['train_asins']} asins; "
        f"val {result['val_rows']} rows / {result['val_asins']} asins",
        f"- CHAMPION (deterministic triage): AUC {ch['auc'] if ch['auc'] is not None else 'n/a'}"
        f" · winners in top {ch['top_n']}: {ch['winners_in_top']}",
        f"- CHALLENGER (classical model, shadow): AUC {xl['auc'] if xl['auc'] is not None else 'n/a'}"
        f" · winners in top {xl['top_n']}: {xl['winners_in_top']}",
        "",
        f"**{result['verdict']}**",
        "",
        "Caveats: backtest rows are the weakest tier (simulated buy cost, no execution/"
        "sell-through); " + (result.get("silver_caveat") or ""),
        "Promotion is HUMAN-ONLY via the brain key scoring.rankingChampion — this job never "
        "touches ai-brain.json.", "",
    ]
    return "\n".join(lines)


def append_report(block: str) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# Ranker report (append-only)\n\nGenerated by scout/train_ranker.py "
                    "(cloud: .github/workflows/train-ranker.yml). Diagnostic + shadow only — "
                    "promotion requires a human brain edit.\n\n")
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")


# --- artifacts + Supabase storage ----------------------------------------------
def save_artifacts(result: Dict[str, Any], out_dir: str) -> List[str]:
    """Persist model.joblib + metrics.json into out_dir. Returns the file paths."""
    import joblib
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    meta = {k: result[k] for k in ("train_rows", "val_rows", "train_asins", "val_asins",
                                   "by_tier", "champion", "challenger", "verdict", "features")}
    meta["trained_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    meta["model_kind"] = "logreg-balanced (interim classical model; V3 LightGBM later)"
    mpath = os.path.join(out_dir, "model.joblib")
    joblib.dump({"model": result["model"], "scaler": result["scaler"],
                 "features": result["features"], "meta": meta}, mpath)
    paths.append(mpath)
    jpath = os.path.join(out_dir, "metrics.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)
    paths.append(jpath)
    return paths


def _storage_headers() -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def upload_to_storage(paths: List[str], date_prefix: str) -> int:
    """Upload artifacts to the private `models` bucket, twice each: versioned
    ranker/<date>/... AND the stable ranker/current/... the local fetch reads. Creates the
    bucket if missing. Returns files uploaded (0 on any hard failure — never raises)."""
    import requests
    supa = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("[train_ranker] no Supabase env — skipping storage upload")
        return 0
    try:
        r = requests.post(f"{supa}/storage/v1/bucket", headers=_storage_headers(),
                          json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=15)
        if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
            print(f"[train_ranker] bucket create: HTTP {r.status_code} (continuing)")
    except Exception as e:
        print(f"[train_ranker] bucket create failed (continuing): {type(e).__name__}")
    n = 0
    import mimetypes
    for path in paths:
        name = os.path.basename(path)
        for prefix in (f"ranker/{date_prefix}", "ranker/current"):
            try:
                with open(path, "rb") as f:
                    r = requests.post(
                        f"{supa}/storage/v1/object/{BUCKET}/{prefix}/{name}",
                        headers={**_storage_headers(), "x-upsert": "true",
                                 "Content-Type": mimetypes.guess_type(name)[0] or "application/octet-stream"},
                        data=f.read(), timeout=60)
                r.raise_for_status()
                n += 1
            except Exception as e:
                print(f"[train_ranker] upload failed ({prefix}/{name}): {type(e).__name__}")
    return n


def fetch_current_model(dest_dir: Optional[str] = None) -> Optional[str]:
    """Download the current champion-candidate (ranker/current/model.joblib) from Supabase
    storage to learning-hub/models/ranker/current/ so the local pipeline has the latest
    cloud-trained model at run start. Best-effort: returns the local path or None; NEVER raises
    (called from run_daily — a storage hiccup must not touch the cycle)."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return None
        dest_dir = dest_dir or os.path.join(MODELS_DIR, "current")
        os.makedirs(dest_dir, exist_ok=True)
        got = None
        for name in ("model.joblib", "metrics.json"):
            r = requests.get(f"{supa}/storage/v1/object/{BUCKET}/ranker/current/{name}",
                             headers=_storage_headers(), timeout=30)
            if r.status_code != 200:
                continue
            p = os.path.join(dest_dir, name)
            with open(p, "wb") as f:
                f.write(r.content)
            if name == "model.joblib":
                got = p
        return got
    except Exception as e:
        print(f"[train_ranker] fetch_current_model failed (non-fatal): {type(e).__name__}")
        return None


# --- Discord -------------------------------------------------------------------
def post_summary(result: Dict[str, Any]) -> bool:
    """One embed to the brain-proposals stream (it's a PROPOSAL surface: the verdict may suggest
    promotion, a human decides). Honest no-op when the webhook isn't configured."""
    import discord_router
    if result.get("refused"):
        embed = {"title": "🤖 Ranker training: refused (not enough data)",
                 "description": result["reason"], "color": 0x8B9BB0}
    else:
        ch, xl = result["champion"], result["challenger"]
        tiers = "; ".join(f"{t}: {c['total']}" for t, c in sorted((result.get("by_tier") or {}).items()))
        embed = {
            "title": "🤖 Ranker trained (shadow) — champion vs challenger",
            "color": 0x3987E5,
            "description": (
                f"Rows: {result['train_rows']}+{result['val_rows']} (by-ASIN split) · tiers: {tiers}\n"
                f"**Champion (triage formula):** AUC {ch['auc'] if ch['auc'] is not None else 'n/a'}, "
                f"{ch['winners_in_top']}/{ch['top_n']} winners in top\n"
                f"**Challenger (model):** AUC {xl['auc'] if xl['auc'] is not None else 'n/a'}, "
                f"{xl['winners_in_top']}/{xl['top_n']} winners in top\n\n{result['verdict']}\n\n"
                "Promotion is human-only: brain key `scoring.rankingChampion` (fba-brain-updater)."),
        }
    return discord_router.send("brain_proposals", [embed], username="FBA Scout — Ranker")


# --- entry point -----------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the shadow ranker + champion/challenger eval.")
    ap.add_argument("--out-dir", default=os.environ.get(
        "RANKER_OUT_DIR", os.path.join(MODELS_DIR, _dt.date.today().isoformat())))
    ap.add_argument("--dry-run", action="store_true", help="no uploads, no Discord post")
    args = ap.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except Exception:
        pass

    assembled = build_dataset()
    result = train_and_evaluate(assembled)
    block = render_report(result)
    append_report(block)
    print(block.encode("ascii", "replace").decode())

    if not result.get("refused") and not args.dry_run:
        paths = save_artifacts(result, args.out_dir)
        uploaded = upload_to_storage(paths, _dt.date.today().isoformat())
        print(f"[train_ranker] artifacts: {len(paths)} saved, {uploaded} uploaded to storage")
    if not args.dry_run:
        post_summary(result)
    # A refusal is an HONEST outcome, not a failure — exit 0 so the scheduled job stays green
    # until data exists; real errors raise and exit non-zero via the traceback.
    return 0


if __name__ == "__main__":
    sys.exit(main())
