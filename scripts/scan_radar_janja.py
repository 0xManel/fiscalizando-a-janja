#!/usr/bin/env python3
"""Radar Janja official-data scanner.

Downloads annual Portal da Transparência travel CSV ZIP files, extracts records
that mention Janja / Rosângela da Silva / Primeira-Dama, classifies each record
conservatively, and writes dashboard-ready JSON + CSV.

Editorial rule: only records with direct official beneficiary match are counted
as direct total. Agenda mentions and presidential-comitiva records stay separate.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
OUT_JSON = OUT_DIR / "radar-janja.json"
OUT_CSV = OUT_DIR / "radar-janja.csv"
PORTAL_DOWNLOAD = "https://portaldatransparencia.gov.br/download-de-dados/viagens/{year}"
YEARS = [2023, 2024, 2025, 2026]

# Contexto externo verificado manualmente: levantamento jornalístico do Poder360
# com dados do Portal da Transparência, publicado em 30/dez/2024.
# Fica separado dos totais automatizados do scanner para não misturar
# dado primário extraído por nós com levantamento secundário/projeção.
STRUCTURE_CONTEXT = {
    "source_name": "Poder360",
    "source_url": "https://www.poder360.com.br/poder-governo/gabinete-de-janja-no-planalto-custa-cerca-de-r-2-mi-por-ano/",
    "published_at": "2024-12-30",
    "official_structure_exists": False,
    "plain_language": "Não existe um gabinete oficial da Primeira-Dama com orçamento próprio. A equipe que a assessora aparece lotada em estruturas da Presidência/Secom, e os gastos são públicos da Presidência, não despesas pessoais dela.",
    "staff_people_reported": 8,
    "average_annual_structure_cost_2023_2024": 1900000.00,
    "total_structure_cost_2023_2024": 3800000.00,
    "monthly_payroll_oct_2024": 118065.68,
    "travel_cost_janja_plus_team_2023_2024": 791542.23,
    "janja_own_travel_reported_2023_2024": 139365.30,
    "janja_own_travel_count_reported_2023_2024": 5,
    "projection_warning": "Qualquer número para 2025/2026 usando a média de R$ 1,9 mi/ano é estimativa, não total oficial consolidado.",
    "estimated_structure_run_rate_monthly": round(1900000.00 / 12, 2),
}

SEARCH_PATTERNS = [
    re.compile(r"\bJANJA\b", re.I),
    re.compile(r"ROS[ÂA]NGELA\s+LULA", re.I),
    re.compile(r"ROS[ÂA]NGELA\s+DA\s+SILVA", re.I),
    re.compile(r"PRIMEIRA[-\s]?DAMA", re.I),
]

DIRECT_NAME_PATTERNS = [
    re.compile(r"^ROS[ÂA]NGELA\s+DA\s+SILVA$", re.I),
    re.compile(r"^JANJA\s+LULA\s+DA\s+SILVA$", re.I),
    re.compile(r"^ROS[ÂA]NGELA\s+LULA\s+DA\s+SILVA$", re.I),
]

PRESIDENTIAL_PATTERNS = [
    re.compile(r"PRESIDENTE\s+DA\s+REP[ÚU]BLICA", re.I),
    re.compile(r"LUI[ZS]\s+IN[ÁA]CIO\s+LULA", re.I),
    re.compile(r"COMITIVA\s+PRESIDENCIAL", re.I),
]

SUPPORT_PATTERNS = [
    re.compile(r"ACOMPANHAR\s+(A|À|A\s+SRA\.?\s+)?PRIMEIRA[-\s]?DAMA", re.I),
    re.compile(r"ASSESSOR(IA)?\s+.*PRIMEIRA[-\s]?DAMA", re.I),
]

COLUMN_ALIASES = {
    "id_processo_viagem": ["Identificador do processo de viagem", "id_viagem", "ID Viagem"],
    "numero_pcdp": ["Número da PCDP", "Numero da PCDP", "Número da Proposta (PCDP)", "Numero da Proposta (PCDP)"],
    "situacao": ["Situação", "Situacao"],
    "urgente": ["Viagem Urgente"],
    "justificativa_urgencia": ["Justificativa Urgência Viagem", "Justificativa Urgencia Viagem"],
    "codigo_orgao_superior": ["Código órgão superior", "Codigo orgao superior", "Código do órgão superior", "Codigo do orgao superior"],
    "nome_orgao_superior": ["Nome órgão superior", "Nome orgao superior", "Nome do órgão superior", "Nome do orgao superior"],
    "codigo_orgao_pagador": ["Código órgão pagador", "Codigo orgao pagador", "Código órgão solicitante", "Codigo orgao solicitante"],
    "nome_orgao_pagador": ["Nome órgão pagador", "Nome orgao pagador", "Nome órgão solicitante", "Nome orgao solicitante"],
    "cpf": ["CPF viajante", "CPF"],
    "nome": ["Nome", "Nome viajante"],
    "cargo": ["Cargo", "Cargo viajante"],
    "funcao": ["Função", "Funcao"],
    "descricao_funcao": ["Descrição Função", "Descricao Funcao"],
    "data_inicio": ["Data início viagem", "Data inicio viagem", "Período - Data de início", "Periodo - Data de inicio"],
    "data_fim": ["Data fim viagem", "Período - Data de fim", "Periodo - Data de fim"],
    "destinos": ["Destinos"],
    "motivo": ["Motivo", "Objetivo da Viagem"],
    "valor_diarias": ["Valor diárias", "Valor diarias"],
    "valor_passagens": ["Valor passagens"],
    "valor_devolucao": ["Valor devolução", "Valor devolucao"],
    "valor_outros": ["Valor outros gastos", "Valor outros"],
}

@dataclass
class Record:
    id: str
    year: int
    file: str
    line_number: int
    date_start: str
    date_end: str
    beneficiary: str
    orgao: str
    orgao_pagador: str
    destination: str
    objective: str
    pcdp: str
    status: str
    urgent: str
    urgency_reason: str
    diarias: float
    passagens: float
    devolucao: float
    outros: float
    total: float
    category: str
    confidence: str
    counted_in_direct_total: bool
    source_label: str
    source_url: str
    evidence: str
    expense_type: str
    expense_label: str
    simple_explanation: str
    waste_signal: str
    date_start_iso: str
    payment_breakdown: dict[str, float]
    ticket_details: list[dict]
    route_segments: list[dict]


def br_money_to_decimal(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    cleaned = value.strip().replace("R$", "").replace(".", "").replace(",", ".")
    if cleaned in {"", "-", "Sem informação"}:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def dec_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def fetch_year_zip(year: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"viagens-{year}.zip"
    if path.exists() and path.stat().st_size > 1024:
        return path
    url = PORTAL_DOWNLOAD.format(year=year)
    print(f"Downloading {url}...", file=sys.stderr)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RadarJanja/0.1"})
    with urlopen(req, timeout=180) as resp:
        data = resp.read()
    if not data.startswith(b"PK"):
        raise RuntimeError(f"Unexpected non-zip response for {year}: {data[:80]!r}")
    path.write_bytes(data)
    time.sleep(0.5)
    return path


def decode_csv(data: bytes) -> str:
    for enc in ("utf-8-sig", "latin1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin1", errors="ignore")


def get_field(row: dict[str, str], key: str) -> str:
    if key in row:
        return (row.get(key) or "").strip()
    for alias in COLUMN_ALIASES.get(key, []):
        if alias in row:
            return (row.get(alias) or "").strip()
    # fallback by normalized headers
    norm_key = normalize(key)
    for k, v in row.items():
        if normalize(k) == norm_key:
            return (v or "").strip()
    return ""


def normalize(text: str) -> str:
    table = str.maketrans("ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇáàãâäéèêëíìîïóòõôöúùûüç", "AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc")
    return re.sub(r"[^a-z0-9]+", "_", text.translate(table).lower()).strip("_")


def line_matches(row_text: str) -> bool:
    return any(pattern.search(row_text) for pattern in SEARCH_PATTERNS)


JANJA_MASKED_CPFS = {"***.222.419-**"}


def classify(name: str, cpf: str, objective: str, orgao: str) -> tuple[str, str, bool]:
    hay = f"{name}\n{objective}\n{orgao}"
    direct_name = any(p.search(name.strip()) for p in DIRECT_NAME_PATTERNS)
    known_janja_cpf = cpf.strip() in JANJA_MASKED_CPFS
    presidential = any(p.search(hay) for p in PRESIDENTIAL_PATTERNS)
    support = any(p.search(hay) for p in SUPPORT_PATTERNS)

    # Conservative rule: exact name alone is not enough because homonyms exist in
    # official databases. Count as direct only when the masked CPF matches the
    # recurring official identifier observed for Rosângela Lula da Silva.
    if direct_name and known_janja_cpf and not presidential:
        return "gasto_direto_identificado", "alta", True
    if direct_name and known_janja_cpf and presidential:
        return "gasto_direto_em_comitiva", "média", False
    if direct_name and not known_janja_cpf:
        return "possivel_homonimo_ou_nao_confirmado", "baixa", False
    if support:
        return "equipe_apoio_primeira_dama", "média", False
    if re.search(r"\bJANJA\b|PRIMEIRA[-\s]?DAMA", hay, re.I) and presidential:
        return "comitiva_presidencial_com_mencao", "média", False
    if re.search(r"\bJANJA\b|PRIMEIRA[-\s]?DAMA", hay, re.I):
        return "agenda_com_mencao", "média", False
    if re.search(r"ROS[ÂA]NGELA\s+DA\s+SILVA", name, re.I):
        return "possivel_homonimo_ou_nao_confirmado", "baixa", False
    return "nao_confirmado", "baixa", False



EXPENSE_TYPE_LABELS = {
    "passagens_aereas": "Passagens / deslocamento",
    "diarias_estadia": "Diárias / estadia",
    "outros_gastos_viagem": "Outros gastos de viagem",
    "alimentacao_comida": "Agenda com almoço/comida",
    "roupa_vestuario": "Roupa / vestuário",
    "agenda_evento": "Agenda / evento oficial",
    "sem_detalhe_suficiente": "Sem detalhe suficiente",
}

WASTE_KEYWORDS = [
    (re.compile(r"PARIS|FRAN[ÇC]A|ROMA|IT[ÁA]LIA|NOVA\s+YORK|LISBOA|DUBAI|CATAR|QATAR|EUROPA", re.I), "viagem internacional cara"),
    (re.compile(r"MODA|ROUPA|VESTU[ÁA]RIO|VESTIMENTA|TRAJE", re.I), "vestuário/roupa"),
    (re.compile(r"REFEI[ÇC][ÃA]O|RESTAURANTE|BUFFET|COMIDA|JANTAR|ALMO[ÇC]O", re.I), "comida/alimentação"),
    (re.compile(r"CERIM[ÔO]NIA|EVENTO|AGENDA|ACOMPANHAR", re.I), "agenda/evento"),
]

def classify_expense_type(objective: str, destination: str, diarias: Decimal, passagens: Decimal, outros: Decimal) -> tuple[str, str, str]:
    """Return machine type, public label and simple explanation.

    Current source is travel data. Clothing/food are only labeled when official
    text explicitly indicates it; otherwise we do not invent the purpose.
    """
    hay = f"{objective} {destination}"
    if re.search(r"MODA|ROUPA|VESTU[ÁA]RIO|VESTIMENTA|TRAJE", hay, re.I):
        return "roupa_vestuario", EXPENSE_TYPE_LABELS["roupa_vestuario"], "O texto oficial menciona roupa/vestuário. Precisa conferência manual antes de virar acusação."
    if re.search(r"REFEI[ÇC][ÃA]O|RESTAURANTE|BUFFET|COMIDA|JANTAR|ALMO[ÇC]O", hay, re.I):
        return "alimentacao_comida", EXPENSE_TYPE_LABELS["alimentacao_comida"], "O texto oficial menciona almoço/refeição/comida na agenda. Não significa nota de restaurante; serve como pista para fiscalizar."
    if passagens >= diarias and passagens >= outros and passagens > 0:
        return "passagens_aereas", EXPENSE_TYPE_LABELS["passagens_aereas"], "Maior parte do valor está em passagens/deslocamento, segundo o CSV oficial de viagens."
    if diarias >= passagens and diarias >= outros and diarias > 0:
        return "diarias_estadia", EXPENSE_TYPE_LABELS["diarias_estadia"], "Maior parte do valor está em diárias/estadia, segundo o CSV oficial de viagens."
    if outros > 0:
        return "outros_gastos_viagem", EXPENSE_TYPE_LABELS["outros_gastos_viagem"], "Há valor em 'outros gastos' no registro oficial, mas o CSV de viagens não detalha nota por nota."
    if re.search(r"CERIM[ÔO]NIA|EVENTO|AGENDA|C[ÚU]PULA|MISS[ÃA]O|REUNI[ÃA]O", hay, re.I):
        return "agenda_evento", EXPENSE_TYPE_LABELS["agenda_evento"], "Registro ligado a agenda/evento oficial. O painel mostra o texto para fiscalização pública."
    return "sem_detalhe_suficiente", EXPENSE_TYPE_LABELS["sem_detalhe_suficiente"], "O registro oficial não detalha a natureza fina do gasto além da viagem."

def waste_signal(total: Decimal, objective: str, destination: str) -> str:
    hay = f"{objective} {destination}"
    signals = [label for pattern, label in WASTE_KEYWORDS if pattern.search(hay)]
    if total >= Decimal("50000"):
        signals.insert(0, "valor muito alto")
    elif total >= Decimal("10000"):
        signals.insert(0, "valor alto")
    return ", ".join(dict.fromkeys(signals)) or "sem alerta automático"

def parse_br_date(value: str) -> str:
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def row_to_record(year: int, file_name: str, line_number: int, row: dict[str, str], row_text: str) -> Record:
    name = get_field(row, "nome")
    objective = get_field(row, "motivo")
    orgao = get_field(row, "nome_orgao_superior")
    orgao_pagador = get_field(row, "nome_orgao_pagador")
    diarias = br_money_to_decimal(get_field(row, "valor_diarias"))
    passagens = br_money_to_decimal(get_field(row, "valor_passagens"))
    devolucao = br_money_to_decimal(get_field(row, "valor_devolucao"))
    outros = br_money_to_decimal(get_field(row, "valor_outros"))
    total = diarias + passagens + outros - devolucao
    cpf = get_field(row, "cpf")
    destination = get_field(row, "destinos")
    expense_type, expense_label, simple_explanation = classify_expense_type(objective, destination, diarias, passagens, outros)
    waste = waste_signal(total, objective, destination)
    category, confidence, counted = classify(name, cpf, objective, f"{orgao} {orgao_pagador}")
    pcdp = get_field(row, "numero_pcdp")
    identifier = get_field(row, "id_processo_viagem") or f"{year}-{file_name}-{line_number}"
    source_url = PORTAL_DOWNLOAD.format(year=year)
    evidence = row_text[:1200]
    return Record(
        id=f"{year}-{identifier}-{line_number}",
        year=year,
        file=file_name,
        line_number=line_number,
        date_start=get_field(row, "data_inicio"),
        date_end=get_field(row, "data_fim"),
        beneficiary=name,
        orgao=orgao,
        orgao_pagador=orgao_pagador,
        destination=destination,
        objective=objective,
        pcdp=pcdp,
        status=get_field(row, "situacao"),
        urgent=get_field(row, "urgente"),
        urgency_reason=get_field(row, "justificativa_urgencia"),
        diarias=dec_to_float(diarias),
        passagens=dec_to_float(passagens),
        devolucao=dec_to_float(devolucao),
        outros=dec_to_float(outros),
        total=dec_to_float(total),
        category=category,
        confidence=confidence,
        counted_in_direct_total=counted,
        source_label=f"Portal da Transparência — Download de Viagens {year} ({file_name}:{line_number})",
        source_url=source_url,
        evidence=evidence,
        expense_type=expense_type,
        expense_label=expense_label,
        simple_explanation=simple_explanation,
        waste_signal=waste,
        date_start_iso=parse_br_date(get_field(row, "data_inicio")),
        payment_breakdown={},
        ticket_details=[],
        route_segments=[],
    )


def read_zip_csv_rows(zf: zipfile.ZipFile, suffix: str) -> Iterable[dict[str, str]]:
    name = next((n for n in zf.namelist() if n.lower().endswith(suffix.lower())), None)
    if not name:
        return []
    text = decode_csv(zf.read(name))
    return csv.DictReader(io.StringIO(text), delimiter=";")


def attach_related_details(records: list[Record]) -> None:
    """Join official payment, ticket and segment files for matched trips only."""
    by_year_id: dict[tuple[int, str], Record] = {}
    for r in records:
        match = re.match(r"^(\d{4})-(.*)-(\d+)$", r.id)
        if match:
            by_year_id[(int(match.group(1)), match.group(2))] = r

    for year in YEARS:
        zip_path = fetch_year_zip(year)
        with zipfile.ZipFile(zip_path) as zf:
            for row in read_zip_csv_rows(zf, "_Pagamento.csv"):
                ident = (row.get("Identificador do processo de viagem") or "").strip()
                rec = by_year_id.get((year, ident))
                if not rec:
                    continue
                tipo = (row.get("Tipo de pagamento") or "Sem tipo informado").strip()
                valor = dec_to_float(br_money_to_decimal(row.get("Valor")))
                rec.payment_breakdown[tipo] = round(rec.payment_breakdown.get(tipo, 0.0) + valor, 2)
            for row in read_zip_csv_rows(zf, "_Passagem.csv"):
                ident = (row.get("Identificador do processo de viagem") or "").strip()
                rec = by_year_id.get((year, ident))
                if not rec:
                    continue
                valor = br_money_to_decimal(row.get("Valor da passagem")) + br_money_to_decimal(row.get("Taxa de serviço"))
                rec.ticket_details.append({
                    "transport": row.get("Meio de transporte") or "",
                    "origin": ", ".join(filter(None, [row.get("Cidade - Origem ida"), row.get("UF - Origem ida"), row.get("País - Origem ida")])),
                    "destination": ", ".join(filter(None, [row.get("Cidade - Destino ida"), row.get("UF - Destino ida"), row.get("País - Destino ida")])),
                    "return_origin": ", ".join(filter(None, [row.get("Cidade - Origem volta"), row.get("UF - Origem volta"), row.get("País - Origem volta")])),
                    "return_destination": ", ".join(filter(None, [row.get("Cidade - Destino volta"), row.get("UF - Destino volta"), row.get("Pais - Destino volta")])),
                    "issue_date": row.get("Data da emissão/compra") or "",
                    "value": dec_to_float(valor),
                })
            for row in read_zip_csv_rows(zf, "_Trecho.csv"):
                ident = (row.get("Identificador do processo de viagem ") or row.get("Identificador do processo de viagem") or "").strip()
                rec = by_year_id.get((year, ident))
                if not rec:
                    continue
                rec.route_segments.append({
                    "sequence": row.get("Sequência Trecho") or "",
                    "origin_date": row.get("Origem - Data") or "",
                    "origin": ", ".join(filter(None, [row.get("Origem - Cidade"), row.get("Origem - UF"), row.get("Origem - País")])),
                    "destination_date": row.get("Destino - Data") or "",
                    "destination": ", ".join(filter(None, [row.get("Destino - Cidade"), row.get("Destino - UF"), row.get("Destino - País")])),
                    "transport": row.get("Meio de transporte") or "",
                    "daily_allowances": row.get("Número Diárias") or "",
                    "mission": row.get("Missao?") or "",
                })


def scan_year(year: int) -> list[Record]:
    zip_path = fetch_year_zip(year)
    records: list[Record] = []
    with zipfile.ZipFile(zip_path) as zf:
        for file_name in zf.namelist():
            if not file_name.lower().endswith(".csv"):
                continue
            text = decode_csv(zf.read(file_name))
            stream = io.StringIO(text)
            reader = csv.DictReader(stream, delimiter=";")
            for line_number, row in enumerate(reader, start=2):
                row_text = ";".join(row.values())
                if line_matches(row_text):
                    records.append(row_to_record(year, file_name, line_number, row, row_text))
    return records


def summarize(records: Iterable[Record]) -> dict:
    recs = list(records)
    by_category: dict[str, dict[str, float | int]] = {}
    by_expense_type: dict[str, dict[str, float | int | str]] = {}
    direct_by_year: dict[str, dict[str, float | int]] = {}
    direct_by_expense_type: dict[str, dict[str, float | int | str]] = {}
    direct_contexts = {"gasto_direto_identificado", "gasto_direto_em_comitiva"}
    for r in recs:
        bucket = by_category.setdefault(r.category, {"count": 0, "total": 0.0})
        bucket["count"] = int(bucket["count"]) + 1
        bucket["total"] = round(float(bucket["total"]) + r.total, 2)
        eb = by_expense_type.setdefault(r.expense_type, {"label": r.expense_label, "count": 0, "total": 0.0})
        eb["count"] = int(eb["count"]) + 1
        eb["total"] = round(float(eb["total"]) + r.total, 2)
        if r.category in direct_contexts:
            yb = direct_by_year.setdefault(str(r.year), {"count": 0, "total": 0.0})
            yb["count"] = int(yb["count"]) + 1
            yb["total"] = round(float(yb["total"]) + r.total, 2)
            db = direct_by_expense_type.setdefault(r.expense_type, {"label": r.expense_label, "count": 0, "total": 0.0})
            db["count"] = int(db["count"]) + 1
            db["total"] = round(float(db["total"]) + r.total, 2)
    sorted_by_date = sorted(recs, key=lambda r: (r.date_start_iso or "0000-00-00", r.total), reverse=True)
    sorted_by_value = sorted(recs, key=lambda r: r.total, reverse=True)
    direct_all_contexts_by_value = [r for r in sorted_by_value if r.category in direct_contexts]
    direct_conservative_by_value = [r for r in sorted_by_value if r.counted_in_direct_total]
    direct_total_all_contexts = round(sum(r.total for r in recs if r.category in direct_contexts), 2)
    direct_total_conservative = round(sum(r.total for r in recs if r.counted_in_direct_total), 2)
    support_and_mentions_total = round(sum(r.total for r in recs if r.category not in direct_contexts), 2)
    return {
        "records": len(recs),
        "janja_direct_total_all_contexts": direct_total_all_contexts,
        "direct_total": direct_total_conservative,
        "identified_total_all_categories": round(sum(r.total for r in recs), 2),
        "support_and_mentions_total": support_and_mentions_total,
        "direct_records_all_contexts": len(direct_all_contexts_by_value),
        "direct_records_conservative": len(direct_conservative_by_value),
        "by_category": by_category,
        "by_expense_type": by_expense_type,
        "direct_by_year": dict(sorted(direct_by_year.items())),
        "direct_by_expense_type": dict(sorted(direct_by_expense_type.items(), key=lambda kv: kv[1]["total"], reverse=True)),
        "structure_context": STRUCTURE_CONTEXT,
        "official_disclaimer": "Não existe número oficial único e consolidado de quanto a Primeira-Dama gastou. Esta página separa viagens oficiais automatizadas, levantamento externo de estrutura/equipe e projeções.",
        "viral_numbers_warning": "Números virais como R$ 63 mi ou R$ 117 mi costumam misturar eventos, reformas, patrimônio da União e comitivas inteiras. Eles não são tratados aqui como gasto pessoal/exclusivo da Janja.",
        "next_monitoring_layers": [
            "Viagens oficiais do Portal da Transparência",
            "Despesas, empenhos e pagamentos",
            "Salários/equipe de apoio",
            "DOU, contratos e SIGA Brasil",
            "Novos registros dos próximos meses"
        ],
        "top_expenses_all": [asdict(r) for r in sorted_by_value[:8]],
        "top_expenses_direct": [asdict(r) for r in direct_all_contexts_by_value[:10]],
        "top_expenses_conservative": [asdict(r) for r in direct_conservative_by_value[:8]],
        "recent_logs": [asdict(r) for r in sorted_by_date[:12]],
        "years": sorted({r.year for r in recs}),
        "official_downloads": [PORTAL_DOWNLOAD.format(year=y) for y in YEARS],
    }


def write_outputs(records: list[Record]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records_sorted = sorted(records, key=lambda r: (r.date_start[-4:] if r.date_start else str(r.year), r.date_start, r.id), reverse=True)
    payload = {
        "project": "Fiscalizando a Janja",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "scope": "Registros oficiais que mencionam Janja, Rosângela da Silva, Primeira-Dama ou agendas associadas. Nesta versão, a fonte primária automatizada é Viagens do Portal da Transparência; roupa/comida só são classificados se aparecerem explicitamente no texto oficial.",
            "counting_rule": "O total direto da Janja soma registros oficiais em nome dela nos dados de viagens. A versão conservadora separa itens em comitiva; equipe, apoio, menções e possíveis homônimos não entram como gasto direto.",
            "structure_note": "Não existe orçamento próprio oficial de gabinete da Primeira-Dama. Estrutura/equipe é tratada como camada separada, baseada em levantamento externo com dados do Portal da Transparência, até automatizarmos folha/despesas/empenhos.",
            "warning": "Base factual para fiscalização cidadã; não afirma crime, irregularidade ou desvio sem fonte jurídica/oficial.",
            "terms": [p.pattern for p in SEARCH_PATTERNS],
        },
        "summary": summarize(records_sorted),
        "records": [asdict(r) for r in records_sorted],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(records_sorted[0]).keys()) if records_sorted else list(Record.__dataclass_fields__.keys()))
        writer.writeheader()
        for r in records_sorted:
            writer.writerow(asdict(r))


def main() -> int:
    all_records: list[Record] = []
    for year in YEARS:
        all_records.extend(scan_year(year))
    attach_related_details(all_records)
    write_outputs(all_records)
    print(json.dumps(summarize(all_records), ensure_ascii=False, indent=2))
    print(f"Wrote {OUT_JSON.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
