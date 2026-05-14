"""
fetch_flights.py
Busca voos programados do dia na API SIROS/ANAC (gratuita, sem autenticacao).
Filtra por aeroporto(s) configurado(s) e salva em data/{ICAO}.json.

Variaveis de ambiente:
  AIRPORTS  -> ICAOs separados por virgula (ex: SBCA,SBGR)
               Padrao: SBCA

Documentacao da API:
  https://sas.anac.gov.br/sas/siros_api/

Endpoints utilizados:
  /api/voos?dataReferencia=DDMMAAAA   -> voos do dia
  /api/aerodromo?sg_aerodromo_icao_ou_iata=ICAO -> dados do aeroporto
"""

import json
import os
from datetime import datetime, timezone, timedelta

import requests

# ── Configuracoes ─────────────────────────────────────────────────────────────

API_BASE     = "https://sas.anac.gov.br/sas/siros_api/api"
airports_env = os.environ.get("AIRPORTS", "SBCA")
AIRPORTS     = [a.strip().upper() for a in airports_env.split(",") if a.strip()]

# Horario de Brasilia: UTC-3
BRT = timezone(timedelta(hours=-3))

# Data de hoje em Brasilia no formato ddMMaaaa exigido pela API
hoje     = datetime.now(BRT)
data_ref = hoje.strftime("%d%m%Y")
data_iso = hoje.strftime("%Y-%m-%d")

print(f"SIROS/ANAC — Buscando voos para: {hoje.strftime('%d/%m/%Y')} (Brasilia)")
print(f"Aeroportos configurados: {', '.join(AIRPORTS)}")

# Mapa de companias aereas (ICAO -> nome)
AIRLINES = {
    "GLO": "GOL",
    "TAM": "LATAM",
    "AZU": "Azul",
    "ONE": "VOEPASS",
    "PTB": "Passaredo",
    "COA": "Copa Airlines",
    "AAL": "American Airlines",
    "UAL": "United Airlines",
    "DAL": "Delta Air Lines",
    "AFR": "Air France",
    "DLH": "Lufthansa",
    "IBE": "Iberia",
    "KLM": "KLM",
    "LAN": "LATAM",
    "AEA": "Air Europa",
}

# Mapa de equipamentos (ICAO -> nome legivel)
EQUIPAMENTOS = {
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A343": "Airbus A340-300",
    "A359": "Airbus A350-900",
    "B737": "Boeing 737",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B38M": "Boeing 737 MAX 8",
    "B763": "Boeing 767-300",
    "B772": "Boeing 777-200",
    "B77W": "Boeing 777-300ER",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "E190": "Embraer E190",
    "E195": "Embraer E195",
    "E295": "Embraer E195-E2",
    "AT76": "ATR 72",
    "AT75": "ATR 72-500",
    "DH8D": "Dash 8-400",
    "C208": "Cessna Caravan",
}

# Mapa de tipos de operacao
TIPO_OPERACAO = {
    "D": "Domestico",
    "I": "Internacional",
}

TIPO_SERVICO = {
    "P": "Passageiros",
    "C": "Carga",
    "M": "Misto",
}


def get_airline_name(icao_empresa: str) -> str:
    if not icao_empresa:
        return "?"
    code = icao_empresa.strip().upper()
    return AIRLINES.get(code, code)


def get_equipment_name(icao_equip: str) -> str:
    if not icao_equip:
        return "?"
    code = icao_equip.strip().upper()
    return EQUIPAMENTOS.get(code, code)


def parse_datetime_brt(dt_str: str) -> str:
    """
    Converte datetime string da API para ISO com BRT.
    """
    if not dt_str:
        return ""

    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(BRT).isoformat()
    except Exception:
        return dt_str


def buscar_voos_do_dia() -> list:
    """
    Busca todos os voos programados para hoje via endpoint /api/voos.
    """
    url = f"{API_BASE}/voos"
    params = {"dataReferencia": data_ref}

    try:
        print(f"\nRequisicao: GET {url}?dataReferencia={data_ref}")

        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()

        raw = r.text.strip()

        # JSON
        if raw.startswith("[") or raw.startswith("{"):
            data = r.json()

            if isinstance(data, list):
                print(f"  Retorno: {len(data)} voos")
                return data

            if isinstance(data, dict):
                for key in ("data", "voos", "result", "results"):
                    if key in data and isinstance(data[key], list):
                        print(f"  Retorno: {len(data[key])} voos")
                        return data[key]

        # CSV
        if ";" in raw:

            linhas = [l for l in raw.splitlines() if l.strip()]

            if not linhas:
                return []

            cabecalho = [c.strip() for c in linhas[0].split(";")]
            dados = linhas[1:]

            result = []

            for linha in dados:
                cols = [c.strip() for c in linha.split(";")]

                voo = {}

                for i, campo in enumerate(cabecalho):
                    voo[campo] = cols[i] if i < len(cols) else ""

                result.append(voo)

            print(f"  Retorno: {len(result)} voos")
            return result

        return []

    except Exception as e:
        print(f"  [ERRO] {e}")
        return []


def buscar_dados_aerodromo(icao: str) -> dict:
    """
    Busca dados complementares do aeroporto.
    """

    url = f"{API_BASE}/aerodromo"

    try:
        r = requests.get(
            url,
            params={"sg_aerodromo_icao_ou_iata": icao},
            timeout=30
        )

        r.raise_for_status()

        data = r.json()

        if isinstance(data, list) and data:
            return data[0]

        if isinstance(data, dict):
            return data

        return {}

    except Exception:
        return {}


def filtrar_e_normalizar(todos_voos: list, icao: str) -> tuple[list, list]:

    chegadas = []
    partidas = []

    for voo in todos_voos:

        origem = (
            voo.get("cd_icao_origem")
            or voo.get("origem")
            or voo.get("aeroporto_origem")
            or ""
        ).strip().upper()

        destino = (
            voo.get("cd_icao_destino")
            or voo.get("destino")
            or voo.get("aeroporto_destino")
            or ""
        ).strip().upper()

        if origem != icao and destino != icao:
            continue

        empresa = (
            voo.get("cd_icao_empresa")
            or voo.get("empresa")
            or ""
        ).strip().upper()

        numero_voo = (
            voo.get("nr_voo")
            or voo.get("numero_voo")
            or ""
        ).strip()

        equipamento = (
            voo.get("cd_icao_equipamento")
            or voo.get("equipamento")
            or ""
        ).strip().upper()

        partida = (
            voo.get("dt_hr_partida_prevista")
            or voo.get("partida_prevista")
            or ""
        )

        chegada = (
            voo.get("dt_hr_chegada_prevista")
            or voo.get("chegada_prevista")
            or ""
        )

        registro = {
            "callsign": f"{empresa}{numero_voo}",
            "numero_voo": numero_voo,
            "airline_icao": empresa,
            "airline": get_airline_name(empresa),
            "equipamento_icao": equipamento,
            "equipamento": get_equipment_name(equipamento),
            "origem_icao": origem,
            "destino_icao": destino,
            "partida_utc": partida,
            "chegada_utc": chegada,
            "partida_brt": parse_datetime_brt(partida),
            "chegada_brt": parse_datetime_brt(chegada),
            "status": "programado",
            "fonte": "SIROS/ANAC",
        }

        if destino == icao:
            registro["rota"] = origem
            chegadas.append(registro)

        if origem == icao:
            registro["rota"] = destino
            partidas.append(registro)

    chegadas.sort(key=lambda x: x.get("chegada_brt") or "")
    partidas.sort(key=lambda x: x.get("partida_brt") or "")

    return chegadas, partidas


# ── Execucao principal ────────────────────────────────────────────────────────

os.makedirs("data", exist_ok=True")

# Busca todos os voos do dia uma unica vez
todos_voos = buscar_voos_do_dia()

if not todos_voos:
    print("\n[AVISO] Nenhum voo retornado pela API.")

# Processa cada aeroporto configurado
for icao in AIRPORTS:

    print(f"\nProcessando {icao}...")

    dados_aerodromo = buscar_dados_aerodromo(icao)

    nome_aerodromo = (
        dados_aerodromo.get("nm_aerodromo")
        or dados_aerodromo.get("nome")
        or dados_aerodromo.get("name")
        or icao
    )

    chegadas, partidas = filtrar_e_normalizar(todos_voos, icao)

    print(f"  Filtrado: {len(chegadas)} chegadas, {len(partidas)} partidas")

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data_referencia": data_iso,
        "airport_icao": icao,
        "airport_name": nome_aerodromo,
        "airport_info": dados_aerodromo,
        "source": "SIROS/ANAC",
        "source_url": "https://sas.anac.gov.br/sas/siros_api/",
        "arrivals": chegadas,
        "departures": partidas,
    }

    path = f"data/{icao}.json"

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print(f"  Salvo em: {path}")

print("\nConcluido.")
