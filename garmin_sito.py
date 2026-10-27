"""Allenamentini: crea un sito con i tuoi allenamenti Garmin e quelli in programma.

La pagina nasce dal modello allenamentini.html (nella stessa cartella).
Con GARMIN_PERSONAL_API_KEY aggiunge i dati di recupero dalla Personal API ufficiale.

Uso:  py garmin_sito.py
Il sito viene salvato in  %USERPROFILE%\\Allenamentini\\index.html  e aperto nel browser.
Rilancia lo script quando vuoi aggiornare i dati.

Su GitHub Actions (variabile CI) gira senza domande: legge i token dalla cartella
indicata in GARMIN_TOKENSTORE e salva il sito in ALLENAMENTINI_OUT.
"""

import json
import os
import sys
import webbrowser
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

TOKENSTORE = str(Path(os.getenv("GARMIN_TOKENSTORE", "~/.garminconnect")).expanduser())
CARTELLA = Path(os.getenv("ALLENAMENTINI_OUT") or Path.home() / "Allenamentini")
AUTOMATICO = bool(os.getenv("CI"))
SETTIMANE_PASSATE = 12
GIORNI_FUTURI = 42


# ---------------------------------------------------------------- accesso

def accedi() -> Garmin:
    try:
        garmin = Garmin()
        garmin.login(TOKENSTORE)
        return garmin
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as err:
        if AUTOMATICO:
            sys.exit(f"Token Garmin non validi o scaduti ({type(err).__name__}): aggiorna il secret GARMINTOKENS.")
        print("Primo accesso: inserisci le credenziali Garmin Connect.")
    garmin = Garmin(
        email=input("Email: ").strip(),
        password=getpass("Password (non viene mostrata mentre scrivi): "),
        prompt_mfa=lambda: input("Codice MFA: ").strip(),
    )
    garmin.login(TOKENSTORE)
    return garmin


def prova(descrizione, funzione, *args, **kwargs):
    """Chiama Garmin; se un dato non è disponibile, continua senza fermarsi."""
    try:
        risultato = funzione(*args, **kwargs)
        print(f"  ok  {descrizione}")
        return risultato
    except Exception as err:  # noqa: BLE001
        print(f"  --  {descrizione}: non disponibile ({type(err).__name__})")
        return None


# ---------------------------------------------------------------- utilità

def primo(d, *chiavi):
    """Primo valore presente tra più chiavi possibili (anche annidate con '.')."""
    if not isinstance(d, dict):
        return None
    for chiave in chiavi:
        valore = d
        for parte in chiave.split("."):
            valore = valore.get(parte) if isinstance(valore, dict) else None
        if valore not in (None, "", []):
            return valore
    return None


def sport_di(chiave: str | None) -> str:
    k = (chiave or "").lower()
    if "run" in k:
        return "corsa"
    if "cycl" in k or "bik" in k or "ride" in k:
        return "bici"
    if "swim" in k:
        return "nuoto"
    if "strength" in k or "training" in k or "cardio" in k or "yoga" in k or "fitness" in k:
        return "forza"
    if "walk" in k or "hik" in k:
        return "camminata"
    return "altro"


def numero(valore):
    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- dati

def attivita(garmin, inizio, oggi):
    grezze = prova("attività", garmin.get_activities_by_date, inizio, oggi) or []
    elenco = []
    for a in grezze:
        tipo = primo(a, "activityType.typeKey") or ""
        distanza = numero(a.get("distance"))
        durata = numero(a.get("duration")) or numero(a.get("movingDuration")) or 0
        elenco.append({
            "id": a.get("activityId"),
            "nome": a.get("activityName") or tipo.replace("_", " ").title(),
            "data": (a.get("startTimeLocal") or "")[:16],
            "sport": sport_di(tipo),
            "km": round(distanza / 1000, 2) if distanza else None,
            "sec": round(durata),
            "fc": numero(a.get("averageHR")),
            "kcal": numero(a.get("calories")),
            "dislivello": numero(a.get("elevationGain")),
            "velocita": numero(a.get("averageSpeed")),
            "te": numero(a.get("aerobicTrainingEffect")),
            "carico": numero(a.get("activityTrainingLoad")),
            "effetto": a.get("trainingEffectLabel"),
            "zone": [round(numero(a.get(f"hrTimeInZone_{z}")) or 0) for z in range(1, 6)],
        })
    return elenco


def piano(garmin, oggi: date):
    """Piano attivo e i suoi allenamenti (Garmin Coach include durata e passo obiettivo)."""
    risposta = prova("piani attivi", garmin.get_active_training_plans, oggi.isoformat()) or {}
    elenco = risposta.get("trainingPlanList") if isinstance(risposta, dict) else risposta
    attivo = next((p for p in elenco or [] if isinstance(p, dict)), None)

    # l'id del piano può mancare nell'elenco: lo cerchiamo anche nel calendario
    calendario = []
    mese = date(oggi.year, oggi.month, 1) - timedelta(days=1)
    mese = date(mese.year, mese.month, 1)
    while mese <= oggi + timedelta(days=GIORNI_FUTURI):
        cal = prova(f"calendario {mese:%m/%Y}", garmin.get_scheduled_workouts, mese.year, mese.month) or {}
        calendario += [i for i in cal.get("calendarItems") or [] if isinstance(i, dict)]
        mese = date(mese.year + (mese.month == 12), mese.month % 12 + 1, 1)
    piano_id = primo(attivo, "trainingPlanId", "id") or next(
        (i.get("trainingPlanId") for i in calendario if i.get("trainingPlanId")), None)

    dettaglio = {}
    if piano_id:
        categoria = (primo(attivo, "trainingPlanCategory") or "").upper()
        if categoria != "PHASED":
            dettaglio = prova("piano adattivo", garmin.get_adaptive_training_plan_by_id, piano_id) or {}
        if not dettaglio.get("taskList"):
            dettaglio = prova("piano", garmin.get_training_plan_by_id, piano_id) or dettaglio

    sedute = []
    for t in dettaglio.get("taskList") or []:
        w = t.get("taskWorkout") or {}
        if w.get("restDay") or not t.get("calendarDate"):
            continue
        stato = (w.get("adaptiveCoachingWorkoutStatus") or "").upper()
        sedute.append({
            "data": t["calendarDate"][:10],
            "titolo": w.get("workoutName") or "Allenamento",
            "descrizione": w.get("workoutDescription"),
            "sport": sport_di(primo(w, "sportType.sportTypeKey")),
            "sec": numero(w.get("estimatedDurationInSecs")),
            "km": None,
            "chiave": bool(t.get("keyWorkout")),
            "lungo": bool(t.get("longWkt")),
            "effetto": w.get("trainingEffectLabel"),
            "fatto": "COMPLETED" in stato,
        })

    # allenamenti messi a mano nel calendario (fuori dal piano)
    gia = {(x["data"], x["titolo"].lower()) for x in sedute}
    for i in calendario:
        if i.get("itemType") not in ("workout", "fbtAdaptiveWorkout", "trainingPlanWorkout"):
            continue
        chiave = (str(i.get("date"))[:10], (i.get("title") or "").lower())
        if chiave in gia or not i.get("date"):
            continue
        gia.add(chiave)
        distanza = numero(i.get("distance"))
        sedute.append({
            "data": chiave[0], "titolo": i.get("title") or "Allenamento", "descrizione": None,
            "sport": sport_di(i.get("sportTypeKey")), "sec": numero(i.get("duration")),
            "km": round(distanza / 1000, 1) if distanza else None,
            "chiave": False, "lungo": False, "effetto": None, "fatto": None,
        })
    sedute.sort(key=lambda x: x["data"])

    info = None
    if attivo or dettaglio:
        fonte = dettaglio or attivo
        info = {
            "nome": primo(fonte, "name", "trainingPlanName") or "Piano di allenamento",
            "inizio": str(primo(fonte, "startDate") or "")[:10],
            "fine": str(primo(fonte, "endDate", "raceDate") or "")[:10],
            "settimane": primo(fonte, "durationInWeeks"),
        }
    return info, sedute


def gara(garmin):
    evento = prova("gara principale", garmin.get_primary_event)
    if not evento:
        prossimi = prova("prossime gare", garmin.get_upcoming_events) or []
        evento = prossimi[0] if isinstance(prossimi, list) and prossimi else None
    if not isinstance(evento, dict):
        return None
    distanza = numero(primo(evento, "eventCustomization.customGoal.distance", "completionTarget.value", "distance"))
    return {
        "nome": primo(evento, "eventName", "title", "name") or "Gara",
        "data": str(primo(evento, "date", "eventDate", "startDate") or "")[:10],
        "luogo": primo(evento, "location", "locationName"),
        "km": round(distanza / 1000, 1) if distanza and distanza > 100 else distanza,
    }


def forma(garmin, oggi):
    risultato = {}
    vo2 = prova("VO2max", garmin.get_max_metrics_latest, oggi) or {}
    risultato["vo2"] = primo(vo2, "generic.vo2MaxPreciseValue", "generic.vo2MaxValue")
    risultato["vo2bici"] = primo(vo2, "cycling.vo2MaxPreciseValue", "cycling.vo2MaxValue")

    stato = prova("stato di allenamento", garmin.get_training_status, oggi) or {}
    dati = primo(stato, "mostRecentTrainingStatus.latestTrainingStatusData") or {}
    dispositivo = next(iter(dati.values()), {}) if isinstance(dati, dict) and dati else {}
    risultato["stato"] = primo(dispositivo, "trainingStatusFeedbackPhrase")
    risultato["acuto"] = primo(dispositivo, "acuteTrainingLoadDTO.dailyTrainingLoadAcute")
    risultato["cronico"] = primo(dispositivo, "acuteTrainingLoadDTO.dailyTrainingLoadChronic")

    previsioni = prova("previsioni gara", garmin.get_race_predictions) or {}
    if isinstance(previsioni, list):
        previsioni = previsioni[0] if previsioni else {}
    risultato["previsioni"] = {
        "5 km": primo(previsioni, "time5K"),
        "10 km": primo(previsioni, "time10K"),
        "Mezza": primo(previsioni, "timeHalfMarathon"),
        "Maratona": primo(previsioni, "timeMarathon"),
    }
    return risultato


def storico(garmin, inizio, oggi):
    """Andamento di VO2max e tempo previsto sulla mezza."""
    vo2 = prova("storico VO2max", garmin.get_max_metrics_range, inizio, oggi, "daily") or []
    previsioni = prova("storico previsioni", garmin.get_race_predictions, inizio, oggi, "daily") or []
    return {
        "vo2": [[primo(v, "generic.calendarDate"), primo(v, "generic.vo2MaxPreciseValue", "generic.vo2MaxValue")]
                for v in vo2 if isinstance(v, dict) and primo(v, "generic.vo2MaxPreciseValue", "generic.vo2MaxValue")],
        "mezza": [[p.get("calendarDate"), p.get("timeHalfMarathon")]
                  for p in previsioni if isinstance(p, dict) and p.get("timeHalfMarathon")],
    }


def recupero(oggi: date):
    """FC a riposo, Body Battery e stress degli ultimi 28 giorni dalla Personal API ufficiale."""
    chiave = os.getenv("GARMIN_PERSONAL_API_KEY", "").strip()
    if not chiave:
        print("  --  recupero: manca GARMIN_PERSONAL_API_KEY")
        return []
    import requests

    base = "https://personal.connectapi.garmin.com"
    try:
        token = requests.post(
            base + "/personalapitoken-service/personal-api/personal-api-key/token",
            headers={"Authorization": f"ApiKey {chiave}"}, timeout=30,
        )
        token.raise_for_status()
        risposta = requests.get(
            base + "/usersummary-service/v2/dailysummaries",
            params={"startDate": (oggi - timedelta(days=27)).isoformat(), "endDate": oggi.isoformat()},
            headers={"Authorization": f"Bearer {token.text.strip()}", "Accept": "application/json"}, timeout=30,
        )
        risposta.raise_for_status()
        giorni = (risposta.json() or {}).get("data") or []
    except Exception as err:  # noqa: BLE001
        print(f"  --  recupero: non disponibile ({type(err).__name__})")
        return []
    print("  ok  recupero (Personal API)")
    return [
        {
            "data": g.get("calendarDate"),
            "riposo": primo(g, "heartRate.restingValue"),
            "bb": primo(g, "bodyBattery.maxValue"),
            "stress": primo(g, "stress.avgLevel"),
            "passi": primo(g, "movement.steps.value"),
        }
        for g in sorted(giorni, key=lambda g: g.get("calendarDate") or "")
        if isinstance(g, dict) and g.get("calendarDate")
    ]


# ---------------------------------------------------------------- main

def main() -> None:
    garmin = accedi()
    oggi = date.today()
    inizio = oggi - timedelta(days=oggi.weekday()) - timedelta(weeks=SETTIMANE_PASSATE - 1)
    print("Scarico i dati da Garmin Connect...")

    dati = {
        "generato": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "oggi": oggi.isoformat(),
        "nome": prova("profilo", garmin.get_full_name) or "",
        "attivita": attivita(garmin, inizio.isoformat(), oggi.isoformat()),
        "gara": gara(garmin),
        "forma": forma(garmin, oggi.isoformat()),
        "storico": storico(garmin, inizio.isoformat(), oggi.isoformat()),
        "recupero": recupero(oggi),
    }
    dati["piano"], dati["sedute"] = piano(garmin, oggi)

    CARTELLA.mkdir(parents=True, exist_ok=True)
    (CARTELLA / "dati.json").write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    modello = Path(__file__).with_name("allenamentini.html").read_text(encoding="utf-8")
    pagina = modello.replace("/*__DATI__*/null", json.dumps(dati, ensure_ascii=False).replace("</", "<\\/"))
    destinazione = CARTELLA / "index.html"
    destinazione.write_text(pagina, encoding="utf-8")

    futuri = [x for x in dati["sedute"] if x["data"] >= dati["oggi"] and not x["fatto"]]
    print(f"\n{len(dati['attivita'])} attività, {len(futuri)} allenamenti in programma.")
    print(f"Sito creato: {destinazione}")
    if not AUTOMATICO:
        webbrowser.open(destinazione.resolve().as_uri())


if __name__ == "__main__":
    main()
