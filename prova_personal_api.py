"""Prova la Garmin Personal API: quali dati restituisce davvero.

Legge la chiave da GARMIN_PERSONAL_API_KEY, la scambia con un token di 24 ore
e interroga alcuni endpoint. Il risultato (stato HTTP e un campione dei dati)
viene salvato in personal_api.json nella cartella ALLENAMENTINI_OUT.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

BASE = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"


def campione(dati):
    """Riduce le liste ai primi elementi, per tenere il resoconto leggibile."""
    if isinstance(dati, list):
        return {"elementi": len(dati), "primi": dati[:2]}
    return dati


def main() -> None:
    chiave = os.getenv("GARMIN_PERSONAL_API_KEY", "").strip()
    if not chiave:
        sys.exit("Manca GARMIN_PERSONAL_API_KEY")

    risposta = requests.post(BASE + TOKEN_PATH, headers={"Authorization": f"ApiKey {chiave}", "Accept": "*/*"}, timeout=30)
    print(f"Scambio chiave -> token: HTTP {risposta.status_code}")
    if not risposta.ok:
        sys.exit(f"La chiave non è stata accettata (HTTP {risposta.status_code})")
    sessione = requests.Session()
    sessione.headers.update({"Authorization": f"Bearer {risposta.text.strip()}", "Accept": "application/json"})

    oggi = date.today()
    ieri = (oggi - timedelta(days=1)).isoformat()
    settimana = (oggi - timedelta(days=7)).isoformat()
    oggi = oggi.isoformat()

    prove = {
        # documentati
        "attività": ("/activitylist-service/activities/search/activities", {"start": 0, "limit": 5}),
        "riepiloghi giornalieri": ("/usersummary-service/v2/dailysummaries", {"startDate": settimana, "endDate": oggi}),
        "sonno": ("/sleep-service/sleep/dailySleep", {"date": ieri}),
        "HRV": (f"/hrv-service/hrv/{ieri}", None),
        "Body Battery": ("/wellness-service/wellness/bodyBattery/reports/daily", {"startDate": settimana, "endDate": oggi}),
        "stress": (f"/usersummary-service/stats/stress/daily/{settimana}/{oggi}", None),
        "zone cardio": ("/biometric-service/heartRateZones/v2", None),
        # non documentati: verifichiamo se ci sono
        "VO2max": (f"/metrics-service/metrics/maxmet/latest/{oggi}", None),
        "stato di allenamento": (f"/metrics-service/metrics/trainingstatus/aggregated/{oggi}", None),
        "allenamenti in programma": ("/workout-service/schedule/workoutScheduleByPeriod", {"startDate": oggi, "endDate": oggi}),
        "piani attivi": ("/trainingplan-service/trainingplan/active-plans", {"startDate": oggi}),
    }

    resoconto = {}
    for nome, (percorso, parametri) in prove.items():
        try:
            r = sessione.get(BASE + percorso, params=parametri, timeout=30)
            try:
                corpo = r.json()
            except ValueError:
                corpo = r.text[:300]
            resoconto[nome] = {"http": r.status_code, "dati": campione(corpo) if r.ok else corpo}
            print(f"  {r.status_code}  {nome}")
        except requests.RequestException as err:
            resoconto[nome] = {"errore": type(err).__name__}
            print(f"  --   {nome}: {type(err).__name__}")

    cartella = Path(os.getenv("ALLENAMENTINI_OUT", "."))
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "personal_api.json").write_text(json.dumps(resoconto, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
