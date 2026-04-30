#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RADAR = PROCESSED / "radar-janja.json"
GOV = PROCESSED / "government-context.json"
OUT = PROCESSED / "dossier-db.json"

FOOD_TERMS = re.compile(r"almo[cç]o|jantar|comida|aliment|restaurante|refei[cç][aã]o|lanche|caf[eé]\b", re.I)
HOTEL_TERMS = re.compile(r"hotel|hosped|estadia|di[aá]ria", re.I)
DIRECT_CATEGORIES = {"gasto_direto_identificado", "gasto_direto_em_comitiva"}
SUPPORT_CATEGORIES = {"equipe_apoio_primeira_dama", "agenda_com_mencao", "comitiva_presidencial_com_mencao"}

def brnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def compact_record(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "year": r.get("year"),
        "date_start": r.get("date_start"),
        "date_start_iso": r.get("date_start_iso"),
        "beneficiary": r.get("beneficiary"),
        "orgao": r.get("orgao_pagador") or r.get("orgao"),
        "destination": r.get("destination"),
        "objective": r.get("objective"),
        "category": r.get("category"),
        "confidence": r.get("confidence"),
        "expense_label": r.get("expense_label"),
        "expense_type": r.get("expense_type"),
        "total": round(brnum(r.get("total")), 2),
        "passagens": round(brnum(r.get("passagens")), 2),
        "diarias": round(brnum(r.get("diarias")), 2),
        "outros": round(brnum(r.get("outros")), 2),
        "counted_in_direct_total": bool(r.get("counted_in_direct_total")),
        "source_label": r.get("source_label"),
        "source_url": r.get("source_url"),
    }

def main() -> None:
    radar = json.loads(RADAR.read_text(encoding="utf-8"))
    gov = json.loads(GOV.read_text(encoding="utf-8"))
    records = radar.get("records", [])
    summary = radar.get("summary", {})
    cpgf = gov.get("cpgf_presidency", {})
    cpgf_total = cpgf.get("total_2023_2026", {})

    direct_travel = [r for r in records if r.get("category") in DIRECT_CATEGORIES or r.get("counted_in_direct_total")]
    support_context = [r for r in records if r.get("category") in SUPPORT_CATEGORIES]
    travel_related = [r for r in records if r.get("expense_type") in {"passagens_deslocamento", "diarias_estadia", "outros_viagem"} or brnum(r.get("passagens")) or brnum(r.get("diarias"))]

    food_clues = []
    lodging_clues = []
    for r in records:
        text = " ".join(str(r.get(k, "")) for k in ["objective", "expense_label", "expense_type", "destination", "beneficiary", "orgao", "orgao_pagador"])
        if FOOD_TERMS.search(text):
            food_clues.append(r)
        if HOTEL_TERMS.search(text):
            lodging_clues.append(r)

    def sum_field(rows: list[dict[str, Any]], field: str) -> float:
        return round(sum(brnum(r.get(field)) for r in rows), 2)

    by_year: dict[str, dict[str, Any]] = {}
    for r in direct_travel:
        year = str(r.get("year") or "sem_ano")
        by_year.setdefault(year, {"count": 0, "total": 0.0, "passagens": 0.0, "diarias": 0.0, "outros": 0.0})
        by_year[year]["count"] += 1
        for field in ["total", "passagens", "diarias", "outros"]:
            by_year[year][field] = round(by_year[year][field] + brnum(r.get(field)), 2)

    db = {
        "project": "Fiscalizando a Janja",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1.0",
        "update_rule": "Gerado por scripts/build_dossier_db.py após scanners oficiais. Mantém camadas separadas para evitar atribuição falsa.",
        "headline": {
            "watched_total_formula": "viagens federais + CPGF Presidência + estrutura/equipe Janja segundo fonte externa",
            "official_travel_federal_total": round(sum(brnum(y.get("total", {}).get("total")) for y in gov.get("official_travel", {}).get("by_year", {}).values()), 2),
            "cpgf_presidency_total": brnum(cpgf_total.get("total")),
            "janja_structure_total_2023_2024": brnum(summary.get("structure_context", {}).get("total_structure_cost_2023_2024")),
            "janja_direct_plus_context_total": brnum(summary.get("janja_direct_total_all_contexts") or summary.get("direct_total")),
            "janja_direct_conservative_total": brnum(summary.get("direct_total")),
        },
        "cache_status": gov.get("cache_status", {}),
        "staff_structure": {
            "title": "Equipe e assessores: estrutura sob lupa",
            "status": "camada 2 em mapeamento oficial",
            "source": "Poder360 com dados públicos; próximos scans devem cruzar SIAPE/DOU quando viável.",
            "average_annual_cost_2023_2024": brnum(summary.get("structure_context", {}).get("average_annual_structure_cost_2023_2024")),
            "total_structure_cost_2023_2024": brnum(summary.get("structure_context", {}).get("total_structure_cost_2023_2024")),
            "monthly_payroll_oct_2024": brnum(summary.get("structure_context", {}).get("monthly_payroll_oct_2024")),
            "known_team_size_estimate": summary.get("structure_context", {}).get("staff_people_reported"),
            "caveat": "Estrutura/equipe é contexto público separado do gasto pessoal direto. Próximo passo é validar servidor por servidor em fontes oficiais pesadas.",
        },
        "cpgf_granular": {
            "title": "CPGF Presidência: mês, sigilo e pistas",
            "scope": cpgf.get("scope_note"),
            "total": cpgf.get("total_2023_2026", {}),
            "secret_summary": cpgf.get("secret_summary", {}),
            "by_month": cpgf.get("by_month", {}),
            "top_favored": cpgf.get("top_favored", [])[:10],
            "top_transaction_types": cpgf.get("top_transaction_types", [])[:8],
            "food_like_top_records": cpgf.get("food_like_top_records", [])[:8],
            "janja_text_mentions": cpgf.get("janja_text_mentions", []),
            "caveat": "CPGF da Presidência é camada de contexto. Sigilo e pistas de alimentação cobram transparência; não provam gasto pessoal da Janja.",
        },
        "investigation_roadmap": [
            {
                "step": "1",
                "title": "Cache oficial e varredura controlada",
                "status": "implantado",
                "public_copy": "A base mostra downloads oficiais em cache. Nada de vender tempo real falso: aqui a pancada vem com método.",
            },
            {
                "step": "2",
                "title": "Equipe/assessores separados",
                "status": "camada criada",
                "public_copy": "Estrutura ligada à primeira-dama fica separada do gasto direto. Próximo alvo: SIAPE, DOU e lotação, servidor por servidor.",
            },
            {
                "step": "3",
                "title": "CPGF granular",
                "status": "implantado",
                "public_copy": "Cartão da Presidência agora tem mês, sigilo, maiores favorecidos e pistas de alimentação. Sem atribuição automática, mas com holofote total.",
            },
        ],
        "travel_food": {
            "title": "Viagens e comidas: onde a conta aparece",
            "editorial_note": "O que tiver fonte entra. O que for só indício fica marcado como pista. Sem maquiagem oficialista. Sem acusação inventada.",
            "direct_travel": {
                "count": len(direct_travel),
                "total": sum_field(direct_travel, "total"),
                "passagens": sum_field(direct_travel, "passagens"),
                "diarias": sum_field(direct_travel, "diarias"),
                "outros": sum_field(direct_travel, "outros"),
                "by_year": by_year,
                "top_records": [compact_record(r) for r in sorted(direct_travel, key=lambda x: brnum(x.get("total")), reverse=True)[:16]],
            },
            "support_and_mentions": {
                "count": len(support_context),
                "total": sum_field(support_context, "total"),
                "top_records": [compact_record(r) for r in sorted(support_context, key=lambda x: brnum(x.get("total")), reverse=True)[:16]],
            },
            "food_like_clues": {
                "official_travel_agenda_count": len(food_clues),
                "official_travel_agenda_total": sum_field(food_clues, "total"),
                "cpgf_presidency_food_like_count": int(cpgf_total.get("food_like_count") or 0),
                "cpgf_presidency_food_like_total": brnum(cpgf_total.get("food_like_total")),
                "top_records": [compact_record(r) for r in sorted(food_clues, key=lambda x: brnum(x.get("total")), reverse=True)[:12]],
            },
            "lodging_daily_clues": {
                "count": len(lodging_clues),
                "total": sum_field(lodging_clues, "total"),
                "diarias": sum_field(lodging_clues, "diarias"),
            },
        },
        "news_links": [
            {
                "layer": "estrutura/equipe",
                "source": "Poder360",
                "title": "Estrutura ligada à Janja custa cerca de R$ 2 mi por ano",
                "url": "https://www.poder360.com.br/poder-governo/gabinete-de-janja-no-planalto-custa-cerca-de-r-2-mi-por-ano/",
                "caveat": "levantamento jornalístico; não é gabinete próprio nem total oficial único",
            },
            {
                "layer": "viagens oficiais",
                "source": "Portal da Transparência",
                "title": "Downloads oficiais de viagens",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
                "caveat": "fonte primária usada no scanner",
            },
            {
                "layer": "cartão corporativo",
                "source": "Portal da Transparência",
                "title": "CPGF — Cartão de Pagamento do Governo Federal",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/cpgf/202604",
                "caveat": "camada Presidência; não é atribuição pessoal automática",
            },
            {
                "layer": "sigilo",
                "source": "Poder360/TCU",
                "title": "TCU mostra sigilo no cartão corporativo da Presidência",
                "url": "https://www.poder360.com.br/poder-governo/tcu-mostra-99-de-sigilo-no-cartao-corporativo-da-presidencia/",
                "caveat": "contexto de opacidade; não identifica beneficiário oculto",
            },
        ],
        "records_index": {
            "total_records": len(records),
            "direct_records": len(direct_travel),
            "support_context_records": len(support_context),
            "travel_related_records": len(travel_related),
            "food_or_meal_clue_records": len(food_clues),
            "source_files": summary.get("official_downloads", []),
        },
    }
    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ dossier db written: {OUT} ({len(records)} records indexed)")

if __name__ == "__main__":
    main()
