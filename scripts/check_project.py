#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "index.html",
    "styles.css",
    "app.js",
    "package.json",
    "vercel.json",
    "scripts/scan_radar_janja.py",
    "scripts/scan_government_context.py",
    "scripts/build_dossier_db.py",
    "data/processed/radar-janja.json",
    "data/processed/government-context.json",
    "data/processed/dossier-db.json",
]

errors: list[str] = []
for rel in REQUIRED:
    path = ROOT / rel
    if not path.exists():
        errors.append(f"missing {rel}")

for rel in ["package.json", "vercel.json", "data/processed/radar-janja.json", "data/processed/government-context.json", "data/processed/dossier-db.json"]:
    path = ROOT / rel
    if path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON {rel}: {exc}")

payload_path = ROOT / "data/processed/radar-janja.json"
if payload_path.exists():
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    for key in ["project", "generated_at", "methodology", "summary", "records"]:
        if key not in payload:
            errors.append(f"payload missing key {key}")
    for idx, rec in enumerate(payload.get("records", [])[:10]):
        for key in ["date_start", "beneficiary", "orgao", "destination", "objective", "total", "category", "confidence", "source_url", "expense_type", "expense_label", "simple_explanation", "waste_signal"]:
            if key not in rec:
                errors.append(f"record {idx} missing {key}")
    summary = payload.get("summary", {})
    for key in ["direct_total", "janja_direct_total_all_contexts", "direct_by_year", "direct_by_expense_type", "by_category", "by_expense_type", "recent_logs", "top_expenses_all", "top_expenses_direct"]:
        if key not in summary:
            errors.append(f"summary missing {key}")

gov_path = ROOT / "data/processed/government-context.json"
if gov_path.exists():
    gov = json.loads(gov_path.read_text(encoding="utf-8"))
    for key in ["project", "generated_at", "debt", "budget", "official_travel", "cpgf_presidency", "sources_map"]:
        if key not in gov:
            errors.append(f"government context missing key {key}")
    for key in ["dbgg_pct_pib", "dlsp_pct_pib"]:
        if key not in gov.get("debt", {}):
            errors.append(f"government debt missing {key}")
    watched = gov.get("budget", {}).get("by_year", {}).get("2026", {}).get("watched_functions", {})
    for key in ["saude", "educacao", "saneamento", "encargos_especiais"]:
        if key not in watched:
            errors.append(f"government budget missing watched function {key}")
    cpgf = gov.get("cpgf_presidency", {})
    if "total_2023_2026" not in cpgf or "by_year" not in cpgf:
        errors.append("government CPGF missing totals/by_year")
    travel = gov.get("official_travel", {})
    if "by_year" not in travel or "presidency_context_2023_2026" not in travel:
        errors.append("government official travel missing totals/presidency context")


dossier_path = ROOT / "data/processed/dossier-db.json"
if dossier_path.exists():
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    for key in ["project", "generated_at", "schema_version", "headline", "cache_status", "staff_structure", "cpgf_granular", "investigation_roadmap", "travel_food", "news_links", "records_index"]:
        if key not in dossier:
            errors.append(f"dossier db missing key {key}")
    tf = dossier.get("travel_food", {})
    for key in ["direct_travel", "support_and_mentions", "food_like_clues", "lodging_daily_clues"]:
        if key not in tf:
            errors.append(f"dossier travel_food missing {key}")

html = (ROOT / "index.html")
app = (ROOT / "app.js")
if html.exists():
    text = html.read_text(encoding="utf-8")
    for token in ["Fiscalizando a JANJA e o PT", "Dinheiro público contra a blindagem", "Veja a conta que o discurso tenta esconder", "Viagens e comidas", "Passos 1, 2 e 3", "O que é de quem", "Links que importam", "Top 10 rastreável", "Prova sem scroll infinito", "Sem fonte, não vira acusação"]:
        if token not in text:
            errors.append(f"index missing token: {token}")
if app.exists():
    text = app.read_text(encoding="utf-8")
    if "data/processed/radar-janja.json" not in text:
        errors.append("app missing data URL")
    if "data/processed/government-context.json" not in text:
        errors.append("app missing government context URL")
    if "data/processed/dossier-db.json" not in text:
        errors.append("app missing dossier db URL")

if errors:
    print("❌ Radar Janja checks failed")
    for err in errors:
        print("-", err)
    raise SystemExit(1)

print("✅ Radar Janja checks passed")
