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


def brl_short(value: Any) -> str:
    n = brnum(value)
    if abs(n) >= 1_000_000_000:
        return f"R$ {n / 1_000_000_000:.2f} bi".replace(".", ",")
    if abs(n) >= 1_000_000:
        return f"R$ {n / 1_000_000:.1f} mi".replace(".", ",")
    if abs(n) >= 1_000:
        return f"R$ {n / 1_000:.1f} mil".replace(".", ",")
    return f"R$ {n:.2f}".replace(".", ",")


def cache_public_status(cache: dict[str, Any]) -> dict[str, Any]:
    travel = cache.get("travel_zips", {}) or {}
    budget = cache.get("budget_zips", {}) or {}
    cpgf = cache.get("cpgf_monthly_zips", {}) or {}
    total_files = int(travel.get("count") or 0) + int(budget.get("count") or 0) + int(cpgf.get("count") or 0)
    total_bytes = int(travel.get("bytes") or 0) + int(budget.get("bytes") or 0) + int(cpgf.get("bytes") or 0)
    return {
        "label": "quase-real por lote oficial",
        "public_summary": f"{total_files} arquivos oficiais em cache local; atualização por varredura, não transmissão ao vivo.",
        "source_first_rule": "Cada atualização reutiliza arquivos oficiais baixados do Portal da Transparência/BCB quando disponíveis; links externos ficam como texto para evitar downloads acidentais.",
        "total_cached_files": total_files,
        "total_cached_mb": round(total_bytes / 1_000_000, 1),
        "latest_official_files": {
            "viagens": travel.get("latest_file"),
            "orcamento": budget.get("latest_file"),
            "cpgf": cpgf.get("latest_file"),
        },
        "caveat": "Fonte oficial primeiro. Cache reduz downloads repetidos, mas novos registros dependem da publicação nos portais públicos.",
    }

def source_scope(layer: str, official_basis: str, *, direct: bool = False, secondary: bool = False) -> dict[str, Any]:
    """Public metadata that keeps source cards from implying personal attribution."""
    return {
        "claim_scope": layer,
        "official_basis": official_basis,
        "included_in_direct_janja_total": bool(direct),
        "source_role": "contexto secundário, fora do total direto" if secondary else "fonte oficial/primária ou base operacional auditável",
    }


def month_label(yyyymm: Any) -> str:
    raw = str(yyyymm or "")
    if len(raw) == 6 and raw.isdigit():
        return f"{raw[4:6]}/{raw[:4]}"
    return raw or "mês sem data"


def record_title(record: dict[str, Any], fallback: str) -> str:
    date = record.get("date_start") or record.get("year") or "sem data"
    place = record.get("destination") or record.get("orgao") or record.get("beneficiary") or "sem destino"
    return f"{fallback}: {date} • {place}"


def latest_budget_year(gov: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the newest budget year available in the official context file."""
    by_year = gov.get("budget", {}).get("by_year", {}) or {}
    years = sorted((str(y) for y in by_year.keys() if str(y).isdigit()), reverse=True)
    if not years:
        return "sem ano", {}
    year = years[0]
    return year, by_year.get(year, {}) or {}


def main() -> None:
    radar = json.loads(RADAR.read_text(encoding="utf-8"))
    gov = json.loads(GOV.read_text(encoding="utf-8"))
    records = radar.get("records", [])
    summary = radar.get("summary", {})
    cpgf = gov.get("cpgf_presidency", {})
    cpgf_total = cpgf.get("total_2023_2026", {})
    budget_year, budget_latest = latest_budget_year(gov)
    budget_total = budget_latest.get("total", {}) or {}
    budget_functions = budget_latest.get("watched_functions", {}) or {}
    sanitation = budget_functions.get("saneamento", {}) or {}
    health = budget_functions.get("saude", {}) or {}

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

    top_direct = max(direct_travel, key=lambda r: brnum(r.get("total")), default={})
    top_support = max(support_context, key=lambda r: brnum(r.get("total")), default={})
    top_food_clue = max(food_clues, key=lambda r: brnum(r.get("total")), default={})
    top_cpgf_month_key, top_cpgf_month = max(
        (cpgf.get("by_month", {}) or {}).items(),
        key=lambda item: brnum(item[1].get("total")),
        default=("", {}),
    )
    source_cards = [
        {
            "layer": "direto Janja",
            "visual_type": "direct",
            "source": "Portal da Transparência",
            "source_type": "fonte oficial primária",
            "credibility": "oficial",
            "stat": brl_short(top_direct.get("total")),
            "title": record_title(top_direct, "Maior registro direto localizado") if top_direct else "Maior registro direto localizado",
            "summary": "Card de prova: mostra a maior linha do recorte direto conservador, sem misturar equipe, comitiva, CPGF ou base federal ampla.",
            "url": top_direct.get("source_url") or "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
            "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
            "caveat": "entra no total direto apenas se a identificação estiver sustentada pela linha oficial",
            **source_scope("maior linha do gasto direto identificado", "Registro oficial de viagem no recorte direto; ranking derivado do scanner", direct=True),
        },
        {
            "layer": "comitiva/equipe",
            "visual_type": "support",
            "source": "Portal da Transparência",
            "source_type": "fonte oficial primária",
            "credibility": "oficial",
            "stat": brl_short(top_support.get("total")),
            "title": record_title(top_support, "Maior apoio/menção separado") if top_support else "Maior apoio/menção separado",
            "summary": "Card de contexto operacional: ajuda a fiscalizar entorno, mas não vira gasto pessoal direto por simples menção.",
            "url": top_support.get("source_url") or "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
            "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
            "caveat": "apoio, menção ou comitiva; fica fora do total direto conservador",
            **source_scope("maior linha de apoio/menção/comitiva", "Registro oficial de viagem classificado como contexto separado"),
        },
        {
            "layer": "pista alimentação",
            "visual_type": "food",
            "source": "Portal da Transparência",
            "source_type": "fonte oficial primária",
            "credibility": "oficial",
            "stat": brl_short(top_food_clue.get("total")),
            "title": record_title(top_food_clue, "Maior pista textual de refeição/agenda") if top_food_clue else "Maior pista textual de refeição/agenda",
            "summary": "Palavra como almoço, refeição ou restaurante é só pista textual. O painel preserva o alerta sem afirmar compra pessoal.",
            "url": top_food_clue.get("source_url") or "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
            "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
            "caveat": "pista textual em fonte oficial; não prova restaurante, roupa, comida ou beneficiário pessoal sem item detalhado",
            **source_scope("pista textual de alimentação/agenda", "Busca de termos em objetivo/categoria oficial; exige leitura manual antes de qualquer afirmação"),
        },
        {
            "layer": "CPGF Presidência",
            "visual_type": "card",
            "source": "Portal da Transparência",
            "source_type": "fonte oficial primária",
            "credibility": "oficial",
            "stat": brl_short(top_cpgf_month.get("total")),
            "title": f"Maior mês CPGF Presidência: {month_label(top_cpgf_month_key)}",
            "summary": "Mostra concentração mensal do cartão da Presidência em base oficial. Mesmo com valores altos ou sigilo, a camada é Presidência/governo, não pessoa física.",
            "url": f"https://portaldatransparencia.gov.br/download-de-dados/cpgf/{top_cpgf_month_key or '202604'}",
            "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
            "caveat": "CPGF Presidência; favorecido sigiloso/opaco não identifica beneficiário pessoal",
            **source_scope("mês mais alto do CPGF Presidência", "Agregado mensal de download oficial CPGF; recorte por unidade Presidência"),
        },
    ]

    db = {
        "project": "Janjômetro",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1.1",
        "update_rule": "Gerado por scripts/build_dossier_db.py após scanners oficiais. Mantém camadas separadas para evitar atribuição falsa.",
        "headline": {
            "watched_total_formula": "todas as viagens federais oficiais + CPGF da Presidência + estrutura/equipe citada em fonte pública; não é gasto pessoal da Janja",
            "public_reading": "O número grande é governo sob lupa: base ampla de viagens federais, CPGF da Presidência e estrutura/equipe. O gasto direto Janja fica em camada própria e não é misturado com contexto.",
            "official_travel_federal_total": round(sum(brnum(y.get("total", {}).get("total")) for y in gov.get("official_travel", {}).get("by_year", {}).values()), 2),
            "cpgf_presidency_total": brnum(cpgf_total.get("total")),
            "janja_structure_total_2023_2024": brnum(summary.get("structure_context", {}).get("total_structure_cost_2023_2024")),
            "janja_direct_plus_context_total": brnum(summary.get("janja_direct_total_all_contexts") or summary.get("direct_total")),
            "janja_direct_conservative_total": brnum(summary.get("direct_total")),
        },
        "cache_status": {
            **gov.get("cache_status", {}),
            "public_status": cache_public_status(gov.get("cache_status", {})),
        },
        "staff_structure": {
            "title": "Equipe e assessores: estrutura sob lupa",
            "status": "equipe/estrutura em apuração",
            "source": "Poder360 com dados públicos; próximos cruzamentos devem conferir SIAPE/DOU quando viável.",
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
            "editorial_note": "O que tiver fonte entra. O que for só indício fica marcado como pista. Fonte primeiro, opinião depois. Sem fonte, não vira afirmação.",
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
        "source_cards": source_cards,
        "news_links": source_cards + [
            {
                "layer": "direto Janja",
                **source_scope("gasto direto identificado", "Registros oficiais de viagens em nome/identificação do recorte Janja; camada conservadora", direct=True),
                "visual_type": "direct",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": brl_short(summary.get("direct_total")),
                "title": "Gasto direto fica em card próprio",
                "summary": "É o recorte mais defensável: registros oficiais ligados diretamente à Janja. Não mistura com equipe, comitiva, Presidência ou macroeconomia.",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
                "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "entra no total direto apenas quando a linha oficial sustenta a identificação",
            },
            {
                "layer": "comitiva/equipe",
                **source_scope("apoio, menções e comitiva", "Registros oficiais de viagens com menção/apoio/comitiva; contexto separado do gasto pessoal direto"),
                "visual_type": "support",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": brl_short(sum_field(support_context, "total")),
                "title": "Apoio e comitiva aparecem, mas separados",
                "summary": "Mostra dinheiro público no entorno operacional. Serve para fiscalização e contexto, sem transformar menção em gasto pessoal.",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
                "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "contexto oficial; não entra no gasto direto conservador",
            },
            {
                "layer": "dívida pública",
                **source_scope("contexto fiscal macro", "Série SGS/BCB; indicador macroeconômico, sem vínculo pessoal"),
                "visual_type": "debt",
                "source": "Banco Central do Brasil — SGS",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": f"{brnum(gov.get('debt', {}).get('dbgg_pct_pib', {}).get('latest_value')):.2f}% do PIB".replace(".", ","),
                "title": "Dívida bruta em série oficial do Banco Central",
                "summary": "Contexto fiscal oficial para ler prioridade de gasto público. Fica fora dos totais Janja/PT e não é atribuição pessoal.",
                "url": gov.get("debt", {}).get("dbgg_pct_pib", {}).get("source_url", "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13762/dados?formato=json"),
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "contexto macro oficial; não é gasto pessoal, partidário ou prova sobre beneficiário específico",
            },
            {
                "layer": "dívida líquida",
                **source_scope("contexto fiscal macro", "Série SGS/BCB; indicador macroeconômico separado de qualquer recorte pessoal"),
                "visual_type": "debt",
                "source": "Banco Central do Brasil — SGS",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": f"{brnum(gov.get('debt', {}).get('dlsp_pct_pib', {}).get('latest_value')):.2f}% do PIB".replace(".", ","),
                "title": "Dívida líquida também vem de série oficial",
                "summary": "Outra lente oficial para pressão fiscal. Entra como contexto macro, não como atribuição a pessoa ou partido.",
                "url": gov.get("debt", {}).get("dlsp_pct_pib", {}).get("source_url", "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4513/dados?formato=json"),
                "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "indicador macro oficial; fora do total direto Janja/PT",
            },
            {
                "layer": "orçamento federal",
                **source_scope("contexto de orçamento da União", f"Download oficial Orçamento da Despesa {budget_year}; base ampla da União, sem atribuição pessoal"),
                "visual_type": "macro",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": brl_short(budget_total.get("realized")),
                "title": f"Orçamento executado da União em {budget_year}",
                "summary": "Mostra a escala do gasto federal para comparar prioridades públicas. É contexto de governo, não total Janja/PT.",
                "url": budget_latest.get("source_url", f"https://portaldatransparencia.gov.br/download-de-dados/orcamento-despesa/{budget_year}"),
                "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "base orçamentária ampla; não é gasto pessoal nem partidário sem prova direta",
            },
            {
                "layer": "prioridades públicas",
                **source_scope("funções monitoradas do orçamento", f"Funções Saúde/Saneamento no Orçamento da Despesa {budget_year}; comparação contextual"),
                "visual_type": "budget",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": f"Saúde {brl_short(health.get('realized'))} / Saneamento {brl_short(sanitation.get('realized'))}",
                "title": f"Saúde e saneamento no orçamento oficial de {budget_year}",
                "summary": "Comparador de prioridade pública em fonte oficial. Ajuda o leitor a dimensionar a base macro sem misturar com gastos diretos.",
                "url": budget_latest.get("source_url", f"https://portaldatransparencia.gov.br/download-de-dados/orcamento-despesa/{budget_year}"),
                "image_policy": "visual editorial gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "comparação de contexto; não entra no placar direto nem prova favorecimento específico",
            },
            {
                "layer": "viagens oficiais",
                **source_scope("base federal ampla de viagens", "Download oficial de viagens do Portal da Transparência; recorte direto Janja é calculado à parte"),
                "visual_type": "travel",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": brl_short(sum(brnum(y.get("total", {}).get("total")) for y in gov.get("official_travel", {}).get("by_year", {}).values())),
                "title": "Downloads oficiais de viagens federais",
                "summary": "Base primária usada para calcular viagens oficiais. É o universo federal sob lupa; o recorte direto Janja aparece separado.",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/viagens/2025",
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "fonte primária usada no scanner; base ampla não é gasto pessoal automático",
            },
            {
                "layer": "cartão corporativo",
                **source_scope("CPGF da Presidência", "Download oficial CPGF; favorecido sigiloso ou unidade Presidência não identifica beneficiário pessoal"),
                "visual_type": "card",
                "source": "Portal da Transparência",
                "source_type": "fonte oficial primária",
                "credibility": "oficial",
                "stat": brl_short(cpgf_total.get("total")),
                "title": "CPGF — Cartão de Pagamento do Governo Federal",
                "summary": "Camada Presidência com totais, meses monitorados e favorecidos agregados. Serve para cobrar transparência, não para atribuir automaticamente a uma pessoa.",
                "url": "https://portaldatransparencia.gov.br/download-de-dados/cpgf/202604",
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "camada Presidência; não é atribuição pessoal automática",
            },
            {
                "layer": "atualização por lote",
                **source_scope("estado do cache/varredura", "Contagem local de ZIPs oficiais já baixados; informa frescor operacional, não novo fato político"),
                "visual_type": "cache",
                "source": "Scanners locais + Portal da Transparência",
                "source_type": "estado técnico auditável",
                "credibility": "operacional",
                "stat": f"{cache_public_status(gov.get('cache_status', {})).get('total_cached_files')} arquivos",
                "title": "Atualização recorrente por lote oficial",
                "summary": cache_public_status(gov.get("cache_status", {})).get("public_summary"),
                "url": "https://portaldatransparencia.gov.br/download-de-dados",
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "quase-real não é live stream: depende de novas publicações oficiais e do cache local",
            },
            {
                "layer": "estrutura/equipe",
                **source_scope("estrutura/equipe em apuração", "Levantamento jornalístico baseado em dados públicos; pendente de reprodução servidor a servidor em base oficial", secondary=True),
                "visual_type": "structure",
                "source": "Poder360",
                "source_type": "contexto jornalístico baseado em dados públicos",
                "credibility": "secundária/contexto",
                "stat": brl_short(summary.get("structure_context", {}).get("average_annual_structure_cost_2023_2024")),
                "title": "Estrutura ligada à Janja custa cerca de R$ 2 mi por ano",
                "summary": "Contexto sobre equipe/estrutura citada publicamente. Fica fora do total direto e pede validação futura em bases oficiais servidor por servidor.",
                "url": "https://www.poder360.com.br/poder-governo/gabinete-de-janja-no-planalto-custa-cerca-de-r-2-mi-por-ano/",
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
                "caveat": "levantamento jornalístico; não é gabinete próprio nem total oficial único",
            },
            {
                "layer": "sigilo",
                **source_scope("opacidade do CPGF", "Contexto institucional sobre sigilo no cartão da Presidência; não revela favorecido oculto", secondary=True),
                "visual_type": "secrecy",
                "source": "Poder360/TCU",
                "source_type": "contexto institucional secundário",
                "credibility": "secundária/contexto",
                "stat": brl_short(cpgf.get("secret_summary", {}).get("total")),
                "title": "TCU mostra sigilo no cartão corporativo da Presidência",
                "summary": "Ajuda a explicar a opacidade da camada CPGF. Sigilo é motivo para fiscalização, não identificação automática de beneficiário.",
                "url": "https://www.poder360.com.br/poder-governo/tcu-mostra-99-de-sigilo-no-cartao-corporativo-da-presidencia/",
                "image_policy": "visual gerado no dashboard; sem scraping ou hotlink de foto",
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
