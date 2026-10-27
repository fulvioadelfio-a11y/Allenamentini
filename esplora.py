"""Esplora la forma dei dati Garmin (libreria non ufficiale + Personal API).

Serve solo durante lo sviluppo: salva un campione delle risposte in esplora.json
(nella cartella ALLENAMENTINI_OUT) per capire quali campi sono disponibili.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from garminconnect import Garmin

from prova_personal_api import BASE, TOKEN_PATH


def riduci(x, profondita=0):
    """Accorcia liste e stringhe lunghe mantenendo la struttura."""
    if isinstance(x, list):
        return [riduci(v, profondita + 1) for v in x[:3]] + ([f"... altri {len(x) - 3}"] if len(x) > 3 else [])
    if isinstance(x, dict):
        return {k: riduci(v, profondita + 1) for k, v in x.items()}
    return x


def main() -> None:
    oggi = date.today()
    d = lambda n: (oggi - timedelta(days=n)).isoformat()  # noqa: E731
    risultati = {}

    def prova(nome, f, *args, **kw):
        try:
            risultati[nome] = riduci(f(*args, **kw))
            print(f"ok  {nome}")
        except Exception as err:  # noqa: BLE001
            risultati[nome] = {"errore": f"{type(err).__name__}: {str(err)[:200]}"}
            print(f"--  {nome}: {type(err).__name__}")

    g = Garmin()
    g.login(os.environ["GARMIN_TOKENSTORE"])
    prova("vo2 giornaliero", g.get_max_metrics_range, d(84), d(0), "daily")
    prova("vo2 settimanale", g.get_max_metrics_range, d(84), d(0), "weekly")
    prova("previsioni giornaliere", g.get_race_predictions, d(84), d(0), "daily")
    prova("attivita (1)", lambda: g.get_activities(0, 1))
    prova("calendario mese", g.get_scheduled_workouts, oggi.year, oggi.month)
    prova("piano adattivo", g.get_scheduled_workouts_by_period, d(0), (oggi + timedelta(days=14)).isoformat())
    prova("stato settimanale", g.get_weekly_training_status, d(84), d(0))
    prova("sonno (non uff.)", g.get_sleep_data, d(1))
    prova("hrv (non uff.)", g.get_hrv_data, d(1))
    cal = g.get_scheduled_workouts(oggi.year, oggi.month) or {}
    adattivi = [i for i in cal.get("calendarItems", []) if i.get("itemType") == "fbtAdaptiveWorkout"]
    if adattivi:
        piano = adattivi[0].get("trainingPlanId")
        prova("piano adattivo dettaglio", g.get_adaptive_training_plan_by_id, piano)
        uuid = adattivi[-1].get("workoutUuid")
        for percorso in (
            f"/workout-service/fbt-adaptive/{uuid}",
            f"/workout-service/workout/FBT_ADAPTIVE/{uuid}",
            f"/workout-service/workout/{uuid}",
        ):
            prova(f"GET {percorso}", g.connectapi, percorso)
    wid = next((i.get("workoutId") for i in cal.get("calendarItems", []) if i.get("itemType") == "workout" and i.get("workoutId")), None)
    if wid:
        prova("dettaglio allenamento", g.get_workout_by_id, wid)

    chiave = os.getenv("GARMIN_PERSONAL_API_KEY")
    if chiave:
        t = requests.post(BASE + TOKEN_PATH, headers={"Authorization": f"ApiKey {chiave}"}, timeout=30).text.strip()
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {t}", "Accept": "application/json"})
        for nome, path, params in [
            ("PA riepiloghi 28g", "/usersummary-service/v2/dailysummaries", {"startDate": d(27), "endDate": d(0)}),
            ("PA sonno 14g", "/sleep-service/sleep/dailySleepSummariesByDate", {"startDate": d(13), "endDate": d(0)}),
            ("PA hrv 14g", f"/hrv-service/hrv/daily/{d(13)}/{d(0)}", None),
        ]:
            r = s.get(BASE + path, params=params, timeout=30)
            try:
                corpo = r.json()
            except ValueError:
                corpo = r.text[:200]
            risultati[nome] = {"http": r.status_code, "dati": riduci(corpo)}
            print(f"{r.status_code} {nome}")

    out = Path(os.getenv("ALLENAMENTINI_OUT", "."))
    out.mkdir(parents=True, exist_ok=True)
    (out / "esplora.json").write_text(json.dumps(risultati, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
