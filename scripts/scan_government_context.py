#!/usr/bin/env python3
"""Generate official government-context data for Fiscalizando a JANJA e o PT.

Keeps this layer separate from Janja-specific totals. Uses public official sources:
- Banco Central SGS for public debt indicators.
- Portal da Transparência bulk downloads for federal budget by function.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
OUT_JSON = OUT_DIR / "government-context.json"

BUDGET_YEARS = [2023, 2024, 2025, 2026]
BUDGET_URL = "https://portaldatransparencia.gov.br/download-de-dados/orcamento-despesa/{year}"
TRAVEL_URL = "https://portaldatransparencia.gov.br/download-de-dados/viagens/{year}"
CPGF_URL = "https://portaldatransparencia.gov.br/download-de-dados/cpgf/{yyyymm}"
BCB_SERIES = {
    "dbgg_pct_pib": {
        "code": "13762",
        "label": "Dívida Bruta do Governo Geral (DBGG)",
        "unit": "% do PIB",
        "why_it_matters": "Mostra o tamanho da dívida bruta pública em relação à economia. Quanto maior, mais pressão sobre juros e orçamento.",
    },
    "dlsp_pct_pib": {
        "code": "4513",
        "label": "Dívida Líquida do Setor Público (DLSP)",
        "unit": "% do PIB",
        "why_it_matters": "Desconta ativos financeiros do setor público. É outra lente oficial para medir endividamento.",
    },
}
WATCH_FUNCTIONS = {
    "Saúde": "saude",
    "Educação": "educacao",
    "Saneamento": "saneamento",
    "Administração": "administracao",
    "Encargos especiais": "encargos_especiais",
    "Assistência social": "assistencia_social",
    "Defesa nacional": "defesa_nacional",
    "Segurança pública": "seguranca_publica",
}

CPGF_FOOD_KEYWORDS = (
    "RESTAUR", "LANCH", "PADARIA", "PANIFIC", "PIZZ", "CHURRASC", "BUFFET",
    "ALIMENT", "REFEIC", "REFEIÇ", "MERCADO", "SUPERMERC", "HORTIFRUT", "CAFE",
)
JANJA_TERMS = ("JANJA", "ROSANGELA", "ROSÂNGELA", "PRIMEIRA-DAMA", "PRIMEIRA DAMA")


def br_decimal(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    cleaned = value.strip().replace("R$", "").replace("%", "").replace(".", "").replace(",", ".")
    if cleaned in {"", "-", "Sem informação"}:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def dec_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def fetch(url: str, timeout: int = 120) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 FiscalizandoJanja/0.3"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_debt_series() -> dict:
    debt = {}
    for key, meta in BCB_SERIES.items():
        # Desde dezembro/2022 para comparar começo do mandato atual com dado mais recente disponível.
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{meta['code']}/dados"
            f"?formato=json&dataInicial={quote('01/12/2022')}&dataFinal={quote('31/12/2026')}"
        )
        data = json.loads(fetch(url, timeout=60).decode("utf-8"))
        rows = sorted(data, key=lambda r: datetime.strptime(r["data"], "%d/%m/%Y"))
        first = rows[0]
        latest = rows[-1]
        first_val = Decimal(first["valor"])
        latest_val = Decimal(latest["valor"])
        debt[key] = {
            **meta,
            "source": "Banco Central do Brasil — SGS",
            "source_url": url,
            "baseline_date": first["data"],
            "baseline_value": dec_float(first_val),
            "latest_date": latest["data"],
            "latest_value": dec_float(latest_val),
            "change_points": dec_float(latest_val - first_val),
            "note": "Comparação em pontos percentuais do PIB desde dez/2022 até o dado mais recente disponível no SGS.",
        }
    return debt


def fetch_budget_zip(year: int) -> bytes:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"orcamento-despesa-{year}.zip"
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    data = fetch(BUDGET_URL.format(year=year), timeout=180)
    if not data.startswith(b"PK"):
        raise RuntimeError(f"Resposta não ZIP para orçamento {year}: {data[:80]!r}")
    path.write_bytes(data)
    return data


def fetch_travel_zip(year: int) -> bytes:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"viagens-{year}.zip"
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    data = fetch(TRAVEL_URL.format(year=year), timeout=180)
    if not data.startswith(b"PK"):
        raise RuntimeError(f"Resposta não ZIP para viagens {year}: {data[:80]!r}")
    path.write_bytes(data)
    return data


def fetch_cpgf_zip(yyyymm: str) -> bytes | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"cpgf-{yyyymm}.zip"
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    try:
        data = fetch(CPGF_URL.format(yyyymm=yyyymm), timeout=120)
    except HTTPError as exc:
        if exc.code in {403, 404, 500}:
            return None
        raise
    except URLError:
        return None
    if not data.startswith(b"PK"):
        return None
    path.write_bytes(data)
    return data


def cache_inventory() -> dict:
    """Expose local bulk-download cache state so the UI can be honest about batch updates."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    groups = {
        "travel_zips": sorted(RAW_DIR.glob("viagens-*.zip")),
        "budget_zips": sorted(RAW_DIR.glob("orcamento-despesa-*.zip")),
        "cpgf_monthly_zips": sorted(RAW_DIR.glob("cpgf-*.zip")),
    }
    def summarize(paths):
        return {
            "count": len(paths),
            "bytes": int(sum(p.stat().st_size for p in paths if p.exists())),
            "latest_file": paths[-1].name if paths else None,
        }
    return {
        "mode": "batch_cached_downloads",
        "rule": "Arquivos oficiais baixados ficam em data/raw e são reutilizados; novas varreduras só baixam o que ainda não está no cache local.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **{name: summarize(paths) for name, paths in groups.items()},
    }


def month_range(start_year: int = 2023) -> list[str]:
    now = datetime.now(timezone.utc)
    out = []
    for year in range(start_year, now.year + 1):
        last_month = now.month if year == now.year else 12
        for month in range(1, last_month + 1):
            out.append(f"{year}{month:02d}")
    return out


def scan_cpgf_presidency() -> dict:
    """Scan official CPGF downloads for Presidency card spending context.

    Government-context only. It is not attributed to Janja unless the official
    CPGF row itself contains a Janja/Primeira-Dama term, which is kept as a
    separate manual-check list and not included in direct Janja totals.
    """
    def fresh_bucket() -> dict:
        return {
            "count": 0,
            "total": Decimal("0"),
            "food_like_count": 0,
            "food_like_total": Decimal("0"),
            "secret_count": 0,
            "secret_total": Decimal("0"),
        }

    by_year = defaultdict(fresh_bucket)
    by_month = defaultdict(fresh_bucket)
    favored = defaultdict(lambda: {"count": 0, "total": Decimal("0")})
    tx_types = defaultdict(lambda: {"count": 0, "total": Decimal("0")})
    food_like_records = []
    janja_mentions = []
    months_ok: list[str] = []
    months_missing: list[str] = []
    for yyyymm in month_range(2023):
        data = fetch_cpgf_zip(yyyymm)
        if data is None:
            months_missing.append(yyyymm)
            continue
        months_ok.append(yyyymm)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            csv_name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                continue
            text = z.read(csv_name).decode("latin1", errors="ignore")
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
            for row in reader:
                org_sup = (row.get("NOME ÓRGÃO SUPERIOR") or "").upper()
                org = (row.get("NOME ÓRGÃO") or "").upper()
                ug = (row.get("NOME UNIDADE GESTORA") or "").upper()
                if "PRESID" not in f"{org_sup} {org} {ug}":
                    continue
                year = str(row.get("ANO EXTRATO") or yyyymm[:4])
                value = br_decimal(row.get("VALOR TRANSAÇÃO"))
                fav = (row.get("NOME FAVORECIDO") or "Sem favorecido informado").strip()
                tx = (row.get("TRANSAÇÃO") or "Sem tipo informado").strip()
                hay = " ".join(str(v or "") for v in row.values()).upper()
                is_food = any(k in hay for k in CPGF_FOOD_KEYWORDS)
                is_secret = "SIGIL" in fav.upper()

                for bucket in (by_year[year], by_month[yyyymm]):
                    bucket["count"] += 1
                    bucket["total"] += value
                    if is_food:
                        bucket["food_like_count"] += 1
                        bucket["food_like_total"] += value
                    if is_secret:
                        bucket["secret_count"] += 1
                        bucket["secret_total"] += value

                favored[fav]["count"] += 1
                favored[fav]["total"] += value
                tx_types[tx]["count"] += 1
                tx_types[tx]["total"] += value

                if is_food:
                    food_like_records.append({
                        "month": yyyymm,
                        "date": row.get("DATA TRANSAÇÃO") or "",
                        "holder": row.get("NOME PORTADOR") or "",
                        "favored": fav,
                        "transaction": tx,
                        "value": dec_float(value),
                        "source_url": CPGF_URL.format(yyyymm=yyyymm),
                        "warning": "Pista por palavra-chave em CPGF/Presidência; não é atribuição pessoal à Janja.",
                    })
                if any(term in hay for term in JANJA_TERMS):
                    janja_mentions.append({
                        "month": yyyymm,
                        "date": row.get("DATA TRANSAÇÃO") or "",
                        "holder": row.get("NOME PORTADOR") or "",
                        "favored": fav,
                        "transaction": tx,
                        "value": dec_float(value),
                        "source_url": CPGF_URL.format(yyyymm=yyyymm),
                        "warning": "Menção textual em CPGF; não entra como gasto direto sem validação manual.",
                    })
    top_favored = sorted(favored.items(), key=lambda kv: kv[1]["total"], reverse=True)[:12]
    top_tx_types = sorted(tx_types.items(), key=lambda kv: kv[1]["total"], reverse=True)[:10]
    food_like_records = sorted(food_like_records, key=lambda r: r["value"], reverse=True)[:20]
    totals = fresh_bucket()
    for vals in by_year.values():
        for k in totals:
            totals[k] += vals[k]

    def encode_bucket(vals: dict) -> dict:
        return {k: (int(v) if k.endswith("count") or k == "count" else dec_float(v)) for k, v in vals.items()}

    secret_ratio = (totals["secret_total"] / totals["total"] * Decimal("100")) if totals["total"] else Decimal("0")
    return {
        "source": "Portal da Transparência — Cartão de Pagamento do Governo Federal (CPGF)",
        "source_url_pattern": CPGF_URL,
        "scope_note": "Camada de contexto: transações CPGF de órgãos/unidades com 'Presid' no nome. Não é gasto pessoal da Janja; comida/alimentação é inferida apenas por palavras no favorecido/transação e deve ser verificada na fonte.",
        "months_scanned": months_ok,
        "months_unavailable_or_blocked": months_missing,
        "total_2023_2026": encode_bucket(totals),
        "secret_summary": {
            "count": int(totals["secret_count"]),
            "total": dec_float(totals["secret_total"]),
            "ratio_of_cpgf_total_pct": float(secret_ratio.quantize(Decimal("0.01"))),
            "caveat": "Favorecido sigiloso não revela quem recebeu. É cobrança por transparência, não atribuição pessoal.",
        },
        "by_year": {year: encode_bucket(vals) for year, vals in sorted(by_year.items())},
        "by_month": {month: encode_bucket(vals) for month, vals in sorted(by_month.items())},
        "top_favored": [
            {"favored": name, "count": int(vals["count"]), "total": dec_float(vals["total"])}
            for name, vals in top_favored
        ],
        "top_transaction_types": [
            {"transaction": name, "count": int(vals["count"]), "total": dec_float(vals["total"])}
            for name, vals in top_tx_types
        ],
        "food_like_top_records": food_like_records,
        "janja_text_mentions": janja_mentions[:20],
    }

def scan_official_travel_context() -> dict:
    """Federal travel totals from official Portal travel downloads.

    Context layer only: these numbers are not Janja spending. They show the size
    of official travel spending in the same source family used by the Janja scan.
    Also keeps top individual travel rows so the public can see where/why the
    biggest official trips appear, without pretending they are personal expenses.
    """
    by_year = {}
    by_org_total = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "diarias": Decimal("0"), "passagens": Decimal("0"), "outros": Decimal("0"), "devolucao": Decimal("0")})
    presidency_aliases = ("PRESID", "GABINETE PESSOAL DO PRESIDENTE", "VICE-PRESID")
    presidency = {"count": 0, "total": Decimal("0"), "diarias": Decimal("0"), "passagens": Decimal("0"), "outros": Decimal("0"), "devolucao": Decimal("0")}
    top_records: list[dict] = []
    top_presidency_records: list[dict] = []

    def field(row: dict, *names: str) -> str:
        for name in names:
            value = row.get(name)
            if value:
                return str(value).strip()
        return ""

    def compact_row(year: int, row: dict, org: str, row_total: Decimal, vals: dict) -> dict:
        return {
            "year": year,
            "pcdp": field(row, "Número da Proposta (PCDP)", "Número da PCDP", "Numero da PCDP"),
            "date_start": field(row, "Período - Data de início", "Data início viagem", "Data inicio viagem"),
            "date_end": field(row, "Período - Data de fim", "Data fim viagem"),
            "beneficiary": field(row, "Nome", "Nome viajante"),
            "org": org,
            "paying_org": field(row, "Nome órgão pagador", "Nome órgão solicitante", "Nome do órgão"),
            "destination": field(row, "Destinos"),
            "objective": field(row, "Motivo", "Objetivo da Viagem"),
            "total": dec_float(row_total),
            "diarias": dec_float(vals["diarias"]),
            "passagens": dec_float(vals["passagens"]),
            "outros": dec_float(vals["outros"]),
            "devolucao": dec_float(vals["devolucao"]),
            "source_url": f"https://portaldatransparencia.gov.br/download-de-dados/viagens/{year}",
            "caveat": "Viagem oficial federal; contexto da estrutura federal, não gasto pessoal automático.",
        }

    def keep_top(bucket: list[dict], item: dict, limit: int = 40) -> None:
        bucket.append(item)
        bucket.sort(key=lambda r: float(r.get("total") or 0), reverse=True)
        del bucket[limit:]

    for year in BUDGET_YEARS:
        z = zipfile.ZipFile(io.BytesIO(fetch_travel_zip(year)))
        csv_name = next(n for n in z.namelist() if n.lower().endswith("_viagem.csv"))
        text = z.read(csv_name).decode("latin1", errors="ignore")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        total = {"count": 0, "total": Decimal("0"), "diarias": Decimal("0"), "passagens": Decimal("0"), "outros": Decimal("0"), "devolucao": Decimal("0")}
        orgs = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "diarias": Decimal("0"), "passagens": Decimal("0"), "outros": Decimal("0"), "devolucao": Decimal("0")})
        for row in reader:
            org = (row.get("Nome do órgão superior") or row.get("Nome órgão superior") or "Sem órgão").strip()
            vals = {
                "diarias": br_decimal(row.get("Valor diárias")),
                "passagens": br_decimal(row.get("Valor passagens")),
                "outros": br_decimal(row.get("Valor outros gastos")),
                "devolucao": br_decimal(row.get("Valor devolução")),
            }
            row_total = vals["diarias"] + vals["passagens"] + vals["outros"] - vals["devolucao"]
            for bucket in (total, orgs[org], by_org_total[org]):
                bucket["count"] += 1
                bucket["total"] += row_total
                for k, v in vals.items():
                    bucket[k] += v
            item = compact_row(year, row, org, row_total, vals)
            keep_top(top_records, item)
            hay = f"{org} {row.get('Nome órgão solicitante') or row.get('Nome órgão pagador') or ''}".upper()
            if any(alias in hay for alias in presidency_aliases):
                presidency["count"] += 1
                presidency["total"] += row_total
                for k, v in vals.items():
                    presidency[k] += v
                keep_top(top_presidency_records, item)
        top_orgs = sorted(orgs.items(), key=lambda kv: kv[1]["total"], reverse=True)[:10]
        by_year[str(year)] = {
            "source": "Portal da Transparência — Viagens",
            "source_url": f"https://portaldatransparencia.gov.br/download-de-dados/viagens/{year}",
            "total": {k: (int(v) if k == "count" else dec_float(v)) for k, v in total.items()},
            "top_orgs_by_total": [{"org": name, **{k: (int(v) if k == "count" else dec_float(v)) for k, v in vals.items()}} for name, vals in top_orgs],
        }
    top_orgs_all = sorted(by_org_total.items(), key=lambda kv: kv[1]["total"], reverse=True)[:12]
    return {
        "source": "Portal da Transparência — Download de Viagens",
        "scope_note": "Total federal de viagens oficiais 2023–2026. É contexto da estrutura federal; não é gasto pessoal da Janja nem do PT.",
        "by_year": by_year,
        "presidency_context_2023_2026": {k: (int(v) if k == "count" else dec_float(v)) for k, v in presidency.items()},
        "top_orgs_2023_2026": [{"org": name, **{k: (int(v) if k == "count" else dec_float(v)) for k, v in vals.items()}} for name, vals in top_orgs_all],
        "top_travel_records_2023_2026": top_records[:20],
        "top_presidency_travel_records_2023_2026": top_presidency_records[:20],
    }


def scan_budget() -> dict:
    by_year = {}
    by_function_total = defaultdict(lambda: {"initial": Decimal("0"), "updated": Decimal("0"), "committed": Decimal("0"), "realized": Decimal("0")})
    for year in BUDGET_YEARS:
        z = zipfile.ZipFile(io.BytesIO(fetch_budget_zip(year)))
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(csv_name).decode("latin1", errors="ignore")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        func = defaultdict(lambda: {"initial": Decimal("0"), "updated": Decimal("0"), "committed": Decimal("0"), "realized": Decimal("0")})
        total = {"initial": Decimal("0"), "updated": Decimal("0"), "committed": Decimal("0"), "realized": Decimal("0")}
        for row in reader:
            name = (row.get("NOME FUNÇÃO") or "Sem função").strip()
            values = {
                "initial": br_decimal(row.get("ORÇAMENTO INICIAL (R$)")),
                "updated": br_decimal(row.get("ORÇAMENTO ATUALIZADO (R$)")),
                "committed": br_decimal(row.get("ORÇAMENTO EMPENHADO (R$)")),
                "realized": br_decimal(row.get("ORÇAMENTO REALIZADO (R$)")),
            }
            for k, v in values.items():
                func[name][k] += v
                total[k] += v
                by_function_total[name][k] += v
        watched = {}
        for label, slug in WATCH_FUNCTIONS.items():
            vals = func.get(label, {"initial": Decimal("0"), "updated": Decimal("0"), "committed": Decimal("0"), "realized": Decimal("0")})
            watched[slug] = {
                "label": label,
                **{k: dec_float(v) for k, v in vals.items()},
            }
        top = sorted(func.items(), key=lambda kv: kv[1]["realized"], reverse=True)[:10]
        by_year[str(year)] = {
            "source": "Portal da Transparência — Orçamento da Despesa",
            "source_url": BUDGET_URL.format(year=year),
            "total": {k: dec_float(v) for k, v in total.items()},
            "watched_functions": watched,
            "top_functions_by_realized": [
                {"label": name, **{k: dec_float(v) for k, v in vals.items()}}
                for name, vals in top
            ],
        }
    watched_total = {}
    for label, slug in WATCH_FUNCTIONS.items():
        vals = by_function_total.get(label, {"initial": Decimal("0"), "updated": Decimal("0"), "committed": Decimal("0"), "realized": Decimal("0")})
        watched_total[slug] = {"label": label, **{k: dec_float(v) for k, v in vals.items()}}
    return {
        "years": BUDGET_YEARS,
        "by_year": by_year,
        "watched_functions_total_2023_2026": watched_total,
        "method_note": "Valores são orçamento/despesa federal por função. 'Realizado' é a coluna oficial do download; não é gasto pessoal de partido ou presidente.",
    }


def build_official_travel_context() -> dict:
    """Lightweight travel context derived from the Janja scanner output.

    This keeps the government-context JSON self-contained for UI/checks while
    avoiding a second heavy parse of travel ZIPs.
    """
    radar_path = OUT_DIR / "radar-janja.json"
    if not radar_path.exists():
        return {"by_year": {}, "presidency_context_2023_2026": {"count": 0, "total": 0.0}}
    data = json.loads(radar_path.read_text(encoding="utf-8"))
    by_year = defaultdict(lambda: {"count": 0, "total": Decimal("0")})
    presidency = {"count": 0, "total": Decimal("0")}
    for rec in data.get("records", []):
        year = str(rec.get("year") or "sem_ano")
        total = Decimal(str(rec.get("total") or 0))
        by_year[year]["count"] += 1
        by_year[year]["total"] += total
        hay = f"{rec.get('orgao','')} {rec.get('orgao_pagador','')} {rec.get('objective','')}".upper()
        if "PRESID" in hay or "PRIMEIRA-DAMA" in hay or "JANJA" in hay:
            presidency["count"] += 1
            presidency["total"] += total
    return {
        "source": "Portal da Transparência — Viagens, via scanner Janja",
        "source_note": "Contexto de viagens oficiais capturado pelo scanner principal. Não é gasto pessoal consolidado; mistura categorias separadas no radar.",
        "by_year": {year: {"count": int(vals["count"]), "total": dec_float(vals["total"])} for year, vals in sorted(by_year.items())},
        "presidency_context_2023_2026": {"count": int(presidency["count"]), "total": dec_float(presidency["total"])}
    }


def build_sources_map() -> dict:
    return {
        "janja_travel": {"status": "integrado", "source": "Portal da Transparência — Viagens 2023–2026", "detail": "Base primária automatizada para viagens diretas/menções/comitiva."},
        "janja_structure": {"status": "contexto externo integrado", "source": "Poder360 com dados do Portal", "detail": "Equipe/estrutura sem gabinete próprio; separado dos totais oficiais automatizados."},
        "federal_budget": {"status": "integrado", "source": "Portal da Transparência — Orçamento da Despesa", "detail": "Saúde, educação, saneamento e demais funções por ano."},
        "public_debt": {"status": "integrado", "source": "Banco Central SGS", "detail": "DBGG e DLSP em % do PIB com variação desde dez/2022."},
        "cpgf_presidency": {"status": "integrado", "source": "Portal da Transparência — CPGF", "detail": "Cartões de pagamento em órgãos/unidades da Presidência; contexto separado, sem atribuir à Janja."},
        "official_travel_context": {"status": "integrado", "source": "Portal da Transparência — Viagens", "detail": "Total federal e recorte Presidência de viagens oficiais; contexto separado dos registros Janja."},
        "expenses_execution": {"status": "mapeado", "source": "Portal da Transparência — Execução da Despesa", "detail": "Próxima camada: empenhos/pagamentos por mês e busca por termos Janja/Primeira-Dama."},
        "servers_payroll": {"status": "mapeado/pesado", "source": "Portal da Transparência — Servidores SIAPE", "detail": "Arquivo mensal grande; precisa varredura controlada para equipe/assessores."},
        "invoices_contracts_bids": {"status": "mapeado", "source": "Notas fiscais, compras e licitações", "detail": "Só marcar comida/roupa se a descrição oficial provar natureza do gasto."},
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "Fiscalizando a JANJA e o PT — contexto governo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "editorial_rule": "Camada de governo é contexto de orçamento federal e dívida. Não deve ser somada ao total Janja nem chamada de gasto pessoal/partidário.",
        "debt": fetch_debt_series(),
        "budget": scan_budget(),
        "official_travel": scan_official_travel_context(),
        "cpgf_presidency": scan_cpgf_presidency(),
        "sources_map": build_sources_map(),
        "cache_status": cache_inventory(),
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT_JSON.relative_to(ROOT)), "debt_latest": {k: v["latest_value"] for k, v in payload["debt"].items()}, "years": BUDGET_YEARS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
