"""Crea un sito (pagina HTML) con i tuoi allenamenti Garmin e quelli in programma.

Uso:  py garmin_sito.py
Il sito viene salvato in  %USERPROFILE%\\GarminSito\\index.html  e aperto nel browser.
Rilancia lo script quando vuoi aggiornare i dati.
"""

import json
import webbrowser
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

TOKENSTORE = str(Path("~/.garminconnect").expanduser())
CARTELLA = Path.home() / "GarminSito"
SETTIMANE_PASSATE = 12
GIORNI_FUTURI = 42


# ---------------------------------------------------------------- accesso

def accedi() -> Garmin:
    try:
        garmin = Garmin()
        garmin.login(TOKENSTORE)
        return garmin
    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
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
        })
    return elenco


def programmati(garmin, oggi: date):
    """Allenamenti futuri: calendario Garmin + piani adattivi (Garmin Coach)."""
    trovati = {}

    def aggiungi(giorno, titolo, sport, sec, km, origine):
        if not giorno or giorno < oggi.isoformat():
            return
        chiave = (giorno, (titolo or "").strip().lower())
        if chiave in trovati:
            return
        trovati[chiave] = {
            "data": giorno, "titolo": titolo or "Allenamento", "sport": sport_di(sport),
            "sec": round(sec) if sec else None,
            "km": round(km / 1000, 1) if km else None, "origine": origine,
        }

    # 1) calendario (mese corrente e successivi)
    mese = date(oggi.year, oggi.month, 1)
    while mese <= oggi + timedelta(days=GIORNI_FUTURI):
        cal = prova(f"calendario {mese:%m/%Y}", garmin.get_scheduled_workouts, mese.year, mese.month) or {}
        for item in cal.get("calendarItems") or []:
            if item.get("itemType") not in ("workout", "trainingPlanWorkout", "fbtAdaptiveWorkout"):
                continue
            aggiungi(
                item.get("date"), item.get("title"),
                primo(item, "sportTypeKey", "activityTypeKey"),
                numero(primo(item, "duration", "estimatedDurationInSecs")),
                numero(primo(item, "distance", "estimatedDistanceInMeters")),
                "calendario",
            )
        mese = date(mese.year + (mese.month == 12), mese.month % 12 + 1, 1)

    # 2) piani adattivi
    fine = (oggi + timedelta(days=GIORNI_FUTURI)).isoformat()
    periodo = prova("piano adattivo", garmin.get_scheduled_workouts_by_period, oggi.isoformat(), fine)
    if isinstance(periodo, dict):
        periodo = primo(periodo, "workoutScheduleList", "scheduledWorkouts", "items") or []
    for item in periodo or []:
        w = item.get("workout") or item
        aggiungi(
            str(primo(item, "calendarDate", "date", "scheduledDate") or "")[:10],
            primo(w, "workoutName", "title", "name"),
            primo(w, "sportType.sportTypeKey", "sportTypeKey"),
            numero(primo(w, "estimatedDurationInSecs", "duration")),
            numero(primo(w, "estimatedDistanceInMeters", "distance")),
            "piano",
        )
    return sorted(trovati.values(), key=lambda x: x["data"])


def piani(garmin, oggi):
    risposta = prova("piani attivi", garmin.get_active_training_plans, oggi) or {}
    elenco = risposta.get("trainingPlanList") if isinstance(risposta, dict) else risposta
    return [
        {
            "nome": primo(p, "name", "trainingPlanName") or "Piano di allenamento",
            "inizio": str(primo(p, "startDate") or "")[:10],
            "fine": str(primo(p, "endDate", "raceDate") or "")[:10],
        }
        for p in (elenco or [])
        if isinstance(p, dict)
    ]


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
        "programmati": programmati(garmin, oggi),
        "piani": piani(garmin, oggi.isoformat()),
        "gara": gara(garmin),
        "forma": forma(garmin, oggi.isoformat()),
    }

    CARTELLA.mkdir(exist_ok=True)
    (CARTELLA / "dati.json").write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    pagina = MODELLO.replace("/*__DATI__*/null", json.dumps(dati, ensure_ascii=False).replace("</", "<\\/"))
    destinazione = CARTELLA / "index.html"
    destinazione.write_text(pagina, encoding="utf-8")

    print(f"\n{len(dati['attivita'])} attività, {len(dati['programmati'])} allenamenti in programma.")
    print(f"Sito creato: {destinazione}")
    webbrowser.open(destinazione.resolve().as_uri())


# ---------------------------------------------------------------- pagina

MODELLO = r'''<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>I miei allenamenti</title>
<style>
:root {
  color-scheme: light;
  --bg: #f4f3ef;
  --surface: #fcfcfb;
  --surface-2: #f0efec;
  --border: #e3e1db;
  --text: #0b0b0b;
  --text-2: #52514e;
  --muted: #7b7a75;
  --grid: #e8e6e0;
  --accent: #2a78d6;
  --corsa: #2a78d6; --bici: #eb6834; --nuoto: #1baf7a; --forza: #eda100; --camminata: #e87ba4; --altro: #8f8e88;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b;
  --shadow: 0 1px 2px rgba(0,0,0,.04), 0 2px 8px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #121211; --surface: #1a1a19; --surface-2: #232321; --border: #2e2e2b;
    --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e88; --grid: #2b2b28; --accent: #3987e5;
    --corsa: #3987e5; --bici: #d95926; --nuoto: #199e70; --forza: #c98500; --camminata: #d55181; --altro: #6f6e69;
    --shadow: none;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --surface-2: #232321; --border: #2e2e2b;
  --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e88; --grid: #2b2b28; --accent: #3987e5;
  --corsa: #3987e5; --bici: #d95926; --nuoto: #199e70; --forza: #c98500; --camminata: #d55181; --altro: #6f6e69;
  --shadow: none;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 28px 16px 56px; }
header { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; margin-bottom: 22px; }
h1 { font-size: 28px; line-height: 1.15; margin: 0; letter-spacing: -.02em; }
.sub { color: var(--muted); font-size: 13px; margin-top: 4px; }
h2 { font-size: 15px; margin: 0 0 14px; letter-spacing: -.005em; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); min-width: 0; }
.grid { display: grid; gap: 14px; margin-bottom: 14px; }
.hero { grid-template-columns: 1.4fr 1fr 1fr; }
.kpis { grid-template-columns: repeat(4, 1fr); }
.two { grid-template-columns: 1.25fr 1fr; }
@media (max-width: 900px) { .hero, .two { grid-template-columns: 1fr; } .kpis { grid-template-columns: repeat(2, 1fr); } }
.label { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.big { font-size: 30px; font-weight: 700; letter-spacing: -.02em; line-height: 1.1; font-variant-numeric: tabular-nums; }
.mid { font-size: 20px; font-weight: 650; letter-spacing: -.01em; line-height: 1.2; }
.meta { color: var(--text-2); font-size: 13.5px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; background: var(--surface-2); font-size: 12.5px; color: var(--text-2); }
.dot { width: 9px; height: 9px; border-radius: 50%; flex: none; display: inline-block; }
.next { border-left: 4px solid var(--accent); }
.next .mid { margin: 8px 0 6px; }
.delta { font-size: 12.5px; color: var(--text-2); margin-top: 6px; }
.delta b { font-weight: 600; }
.bar-track { height: 8px; border-radius: 4px; background: var(--surface-2); overflow: hidden; margin-top: 10px; }
.bar-fill { height: 100%; background: var(--accent); border-radius: 4px; }
.status { display: inline-flex; align-items: center; gap: 6px; font-weight: 650; font-size: 18px; margin-top: 6px; }
.status svg { flex: none; }
/* grafico */
.chart-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.chart-head h2 { margin: 0; }
.seg { display: inline-flex; background: var(--surface-2); border-radius: 9px; padding: 3px; }
.seg button { border: 0; background: transparent; color: var(--text-2); font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 7px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--surface); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,.08); font-weight: 600; }
.legend { display: flex; gap: 16px; font-size: 12.5px; color: var(--text-2); margin-bottom: 4px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
#chart { position: relative; }
#chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.tip { position: absolute; pointer-events: none; background: var(--text); color: var(--surface); font-size: 12.5px; padding: 8px 10px; border-radius: 8px; white-space: nowrap; transform: translate(-50%, -100%); opacity: 0; transition: opacity .1s; z-index: 2; }
.tip b { font-weight: 650; }
/* liste */
.week-group + .week-group { margin-top: 14px; }
.week-title { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
.plan-item { display: grid; grid-template-columns: 52px 1fr auto; gap: 12px; align-items: center; padding: 9px 0; border-top: 1px solid var(--border); }
.plan-item:first-of-type { border-top: 0; }
.day { text-align: center; line-height: 1.1; }
.day b { display: block; font-size: 18px; font-variant-numeric: tabular-nums; }
.day small { color: var(--muted); font-size: 11.5px; text-transform: uppercase; }
.plan-item .t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
.plan-item .n { color: var(--text-2); font-size: 13px; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.today .day b { color: var(--accent); }
.sport-row { display: grid; grid-template-columns: 96px 1fr 64px; gap: 10px; align-items: center; font-size: 13.5px; padding: 5px 0; }
.sport-row .track { height: 14px; }
.sport-row .fill { height: 14px; border-radius: 0 4px 4px 0; min-width: 2px; }
.sport-row .v { text-align: right; color: var(--text-2); font-variant-numeric: tabular-nums; }
.preds { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 18px; }
.pred { background: var(--surface-2); border-radius: 10px; padding: 10px 12px; }
.pred b { display: block; font-size: 17px; font-variant-numeric: tabular-nums; }
.pred span { font-size: 12px; color: var(--muted); }
@media (max-width: 520px) { .preds { grid-template-columns: repeat(2, 1fr); } }
/* tabella */
.table-wrap { overflow-x: auto; margin: 0 -18px; padding: 0 18px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { text-align: left; font-size: 11.5px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; padding: 0 10px 8px; white-space: nowrap; }
td { padding: 10px; border-top: 1px solid var(--border); white-space: nowrap; font-variant-numeric: tabular-nums; }
td.name { white-space: normal; min-width: 180px; font-weight: 600; }
td.name a { color: inherit; text-decoration: none; }
td.name a:hover { text-decoration: underline; }
th.r, td.r { text-align: right; }
tr:hover td { background: var(--surface-2); }
.empty { color: var(--muted); font-size: 14px; padding: 10px 0; }
footer { color: var(--muted); font-size: 12.5px; margin-top: 22px; text-align: center; }
.theme-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-2); border-radius: 9px; padding: 6px 12px; font: inherit; font-size: 13px; cursor: pointer; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1 id="titolo">I miei allenamenti</h1>
      <div class="sub" id="aggiornato"></div>
    </div>
    <button class="theme-btn" id="tema" type="button">Tema chiaro/scuro</button>
  </header>

  <section class="grid hero">
    <div class="card next" id="prossimo"></div>
    <div class="card" id="gara"></div>
    <div class="card" id="piano"></div>
  </section>

  <section class="grid kpis" id="kpis"></section>

  <section class="card" style="margin-bottom:14px">
    <div class="chart-head">
      <h2>Volume settimanale</h2>
      <div class="seg" role="group" aria-label="Unità">
        <button type="button" data-m="ore" aria-pressed="true">Ore</button>
        <button type="button" data-m="km" aria-pressed="false">Km</button>
      </div>
    </div>
    <div class="legend">
      <span><i class="sw" style="background:var(--accent)"></i>Svolto</span>
      <span><svg width="12" height="12" aria-hidden="true"><rect x=".75" y=".75" width="10.5" height="10.5" rx="2.5" fill="url(#hatch-l)" stroke="var(--accent)" stroke-width="1.5"/></svg>In programma</span>
    </div>
    <div id="chart"><div class="tip" id="tip"></div></div>
  </section>

  <section class="grid two">
    <div class="card">
      <h2>In programma</h2>
      <div id="programma"></div>
    </div>
    <div class="card">
      <h2>Ultime 4 settimane per sport</h2>
      <div id="sport"></div>
      <div class="preds" id="previsioni"></div>
    </div>
  </section>

  <section class="card">
    <h2>Ultime attività</h2>
    <div class="table-wrap"><table id="tabella"></table></div>
  </section>

  <footer>Dati da Garmin Connect · rilancia <code>garmin_sito.py</code> per aggiornare</footer>
</div>

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <pattern id="hatch-l" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="5" height="5" fill="var(--surface)"/>
      <line x1="0" y1="0" x2="0" y2="5" stroke="var(--accent)" stroke-width="1.6" opacity=".55"/>
    </pattern>
  </defs>
</svg>

<script>
const DATI = /*__DATI__*/null || demo();

const SPORT = {
  corsa: "Corsa", bici: "Bici", nuoto: "Nuoto", forza: "Forza", camminata: "Camminata", altro: "Altro",
};
const GIORNI = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const d = (s) => { const [y, m, g] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, g); };
const iso = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
const lunedi = (x) => { const r = new Date(x); r.setDate(r.getDate() - ((r.getDay() + 6) % 7)); return r; };
const addGiorni = (x, n) => { const r = new Date(x); r.setDate(r.getDate() + n); return r; };
const giorniTra = (a, b) => Math.round((b - a) / 86400000);
const durata = (s) => { if (!s) return "–"; const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h}h ${String(m).padStart(2, "0")}'` : `${m}'`; };
const orologio = (s) => { if (!s) return "–"; s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(x).padStart(2, "0")}`; };
const num = (v, dec = 1) => v == null ? "–" : v.toLocaleString("it-IT", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const dataBreve = (s) => { const x = d(s); return `${GIORNI[x.getDay()]} ${x.getDate()} ${MESI[x.getMonth()]}`; };
const ritmo = (a) => {
  if (!a.velocita) return "–";
  if (a.sport === "corsa" || a.sport === "camminata") { const sec = 1000 / a.velocita; return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")} /km`; }
  if (a.sport === "nuoto") { const sec = 100 / a.velocita; return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")} /100m`; }
  return `${num(a.velocita * 3.6)} km/h`;
};
const pallino = (sport) => `<i class="dot" style="background:var(--${sport in SPORT ? sport : "altro"})"></i>`;

const OGGI = d(DATI.oggi);
const ATT = [...DATI.attivita].sort((a, b) => b.data.localeCompare(a.data));
const PROG = DATI.programmati || [];

// ------------------------------------------------------------ intestazione
$("titolo").textContent = DATI.nome ? `Allenamenti di ${DATI.nome.split(" ")[0]}` : "I miei allenamenti";
$("aggiornato").textContent = `Aggiornato il ${DATI.generato}`;

// ------------------------------------------------------------ prossimo allenamento
(() => {
  const p = PROG[0];
  if (!p) { $("prossimo").innerHTML = `<div class="label">Prossimo allenamento</div><div class="mid" style="margin-top:8px">Nessun allenamento in programma</div><div class="meta">Aggiungi un piano o un allenamento al calendario di Garmin Connect.</div>`; return; }
  const gg = giorniTra(OGGI, d(p.data));
  const quando = gg === 0 ? "Oggi" : gg === 1 ? "Domani" : dataBreve(p.data);
  $("prossimo").innerHTML = `
    <div class="label">Prossimo allenamento · ${quando}</div>
    <div class="mid">${esc(p.titolo)}</div>
    <div class="row">
      <span class="chip">${pallino(p.sport)}${SPORT[p.sport]}</span>
      ${p.sec ? `<span class="chip">${durata(p.sec)}</span>` : ""}
      ${p.km ? `<span class="chip">${num(p.km)} km</span>` : ""}
      ${gg > 1 ? `<span class="chip">tra ${gg} giorni</span>` : ""}
    </div>`;
})();

// ------------------------------------------------------------ gara
(() => {
  const g = DATI.gara;
  if (!g || !g.data) { $("gara").innerHTML = `<div class="label">Gara obiettivo</div><div class="mid" style="margin-top:8px">Nessuna gara</div><div class="meta">Aggiungi una gara al calendario Garmin per vedere il conto alla rovescia.</div>`; return; }
  const gg = giorniTra(OGGI, d(g.data));
  $("gara").innerHTML = `
    <div class="label">Gara obiettivo</div>
    <div class="big" style="margin-top:8px">${gg >= 0 ? gg : "–"}<span class="meta" style="font-size:14px;font-weight:500"> giorni</span></div>
    <div class="meta" style="margin-top:4px"><b style="color:var(--text)">${esc(g.nome)}</b><br>${dataBreve(g.data)} ${d(g.data).getFullYear()}${g.km ? ` · ${num(g.km)} km` : ""}${g.luogo ? ` · ${esc(g.luogo)}` : ""}</div>`;
})();

// ------------------------------------------------------------ piano
(() => {
  const p = (DATI.piani || [])[0];
  const prossimi7 = PROG.filter((x) => giorniTra(OGGI, d(x.data)) < 7);
  if (!p) {
    $("piano").innerHTML = `<div class="label">Prossimi 7 giorni</div><div class="big" style="margin-top:8px">${prossimi7.length}</div><div class="meta">allenamenti in programma · ${durata(prossimi7.reduce((s, x) => s + (x.sec || 0), 0))}</div>`;
    return;
  }
  let pct = null, sett = "";
  if (p.inizio && p.fine) {
    const tot = giorniTra(d(p.inizio), d(p.fine)), fatto = giorniTra(d(p.inizio), OGGI);
    pct = Math.max(0, Math.min(100, Math.round((fatto / tot) * 100)));
    sett = `Settimana ${Math.min(Math.ceil(tot / 7), Math.floor(fatto / 7) + 1)} di ${Math.ceil(tot / 7)}`;
  }
  $("piano").innerHTML = `
    <div class="label">Piano attivo</div>
    <div class="mid" style="margin-top:8px">${esc(p.nome)}</div>
    <div class="meta">${sett}${sett ? " · " : ""}${prossimi7.length} ${prossimi7.length === 1 ? "allenamento" : "allenamenti"} nei prossimi 7 giorni</div>
    ${pct != null ? `<div class="bar-track" role="img" aria-label="Avanzamento ${pct}%"><div class="bar-fill" style="width:${pct}%"></div></div><div class="delta">${pct}% completato · fine ${dataBreve(p.fine)}</div>` : ""}`;
})();

// ------------------------------------------------------------ KPI
(() => {
  const inizio = lunedi(OGGI);
  const tra = (a, b) => ATT.filter((x) => { const t = d(x.data); return t >= a && t < b; });
  const somma = (l) => ({ n: l.length, km: l.reduce((s, x) => s + (x.km || 0), 0), sec: l.reduce((s, x) => s + (x.sec || 0), 0) });
  const q = somma(tra(inizio, addGiorni(inizio, 7)));
  // settimana scorsa fino allo stesso giorno, per un confronto alla pari
  const s = somma(tra(addGiorni(inizio, -7), addGiorni(OGGI, -6)));
  const m4 = somma(tra(addGiorni(inizio, -21), addGiorni(inizio, 7)));
  const f = DATI.forma || {};
  const diff = (a, b, fmt) => { const v = a - b; return v === 0 ? "come la settimana scorsa a quest'ora" : `<b>${v > 0 ? "+" : "−"}${fmt(Math.abs(v))}</b> vs settimana scorsa a quest'ora`; };

  const STATI = {
    PRODUCTIVE: ["Produttivo", "good"], PEAKING: ["Picco di forma", "good"], MAINTAINING: ["Mantenimento", "good"],
    RECOVERY: ["Recupero", "warning"], UNPRODUCTIVE: ["Non produttivo", "serious"], DETRAINING: ["Perdita di forma", "serious"],
    OVERREACHING: ["Sovraccarico", "critical"], STRAINED: ["Affaticato", "critical"], NO_STATUS: ["Nessuno stato", null],
  };
  const chiave = Object.keys(STATI).find((k) => (f.stato || "").toUpperCase().startsWith(k));
  const [statoTesto, statoTono] = chiave ? STATI[chiave] : [null, null];
  const icona = { good: '<path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>', warning: '<path d="M8 3v6M8 12.5v.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>', serious: '<path d="M8 3v6M8 12.5v.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>', critical: '<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' };

  $("kpis").innerHTML = `
    <div class="card"><div class="label">Questa settimana</div>
      <div class="big" style="margin-top:8px">${durata(q.sec)}</div>
      <div class="meta">${q.n} ${q.n === 1 ? "allenamento" : "allenamenti"} · ${num(q.km)} km</div>
      <div class="delta">${diff(q.sec, s.sec, durata)}</div></div>
    <div class="card"><div class="label">Ultime 4 settimane</div>
      <div class="big" style="margin-top:8px">${num(m4.km, 0)} <span class="meta" style="font-size:14px;font-weight:500">km</span></div>
      <div class="meta">${m4.n} ${m4.n === 1 ? "allenamento" : "allenamenti"} · ${durata(m4.sec)}</div>
      <div class="delta">media ${durata(m4.sec / 4)} a settimana</div></div>
    <div class="card"><div class="label">VO2max</div>
      <div class="big" style="margin-top:8px">${f.vo2 != null ? Math.round(f.vo2) : "–"}</div>
      <div class="meta">${f.vo2bici != null ? `bici ${Math.round(f.vo2bici)} · ` : ""}ml/kg/min</div></div>
    <div class="card"><div class="label">Stato di allenamento</div>
      ${statoTesto ? `<div class="status"><svg width="16" height="16" viewBox="0 0 16 16" style="color:var(--${statoTono || "muted"})" aria-hidden="true">${icona[statoTono] || ""}</svg>${statoTesto}</div>` : `<div class="mid" style="margin-top:8px">–</div>`}
      <div class="meta" style="margin-top:4px">${f.acuto != null ? `Carico acuto ${Math.round(f.acuto)}` : ""}${f.cronico != null ? ` · cronico ${Math.round(f.cronico)}` : ""}</div></div>`;
})();

// ------------------------------------------------------------ grafico settimanale
const SETTIMANE = (() => {
  const primoLun = lunedi(OGGI);
  const settimane = [];
  for (let i = -11; i <= 5; i++) {
    const inizio = addGiorni(primoLun, i * 7), fine = addGiorni(inizio, 7);
    const dentro = (x) => { const t = d(x.data); return t >= inizio && t < fine; };
    const fatte = ATT.filter(dentro), prev = PROG.filter(dentro);
    settimane.push({
      inizio, corrente: i === 0, futura: i > 0,
      ore: fatte.reduce((s, x) => s + (x.sec || 0), 0) / 3600, km: fatte.reduce((s, x) => s + (x.km || 0), 0), n: fatte.length,
      oreP: prev.reduce((s, x) => s + (x.sec || 0), 0) / 3600, kmP: prev.reduce((s, x) => s + (x.km || 0), 0), nP: prev.length,
    });
  }
  while (settimane.length > 12 && settimane.at(-1).futura && settimane.at(-1).nP === 0) settimane.pop();
  return settimane;
})();
let misura = "ore";

function disegna() {
  const box = $("chart");
  const W = Math.max(320, box.clientWidth), H = 240, pl = 36, pr = 6, pt = 12, pb = 28;
  const k = misura, kp = misura + "P";
  const max = Math.max(1, ...SETTIMANE.map((s) => s[k] + s[kp]));
  const passo = misura === "ore" ? (max > 12 ? 4 : max > 6 ? 2 : 1) : (max > 120 ? 40 : max > 60 ? 20 : max > 25 ? 10 : 5);
  const top = Math.ceil(max / passo) * passo;
  const y = (v) => pt + (H - pt - pb) * (1 - v / top);
  const colW = (W - pl - pr) / SETTIMANE.length, bw = Math.min(30, colW * 0.62);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Volume settimanale in ${misura}">`;
  for (let v = 0; v <= top; v += passo) {
    svg += `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)" stroke-width="1"/>`;
    svg += `<text x="${pl - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${v}${misura === "ore" ? "h" : ""}</text>`;
  }
  const r = 4;
  const barra = (x, y0, y1, arrotonda, attr) => {
    const h = y0 - y1; if (h <= 0.5) return "";
    const rr = arrotonda ? Math.min(r, h, bw / 2) : 0;
    return `<path d="M${x},${y0} V${y1 + rr} Q${x},${y1} ${x + rr},${y1} H${x + bw - rr} Q${x + bw},${y1} ${x + bw},${y1 + rr} V${y0} Z" ${attr}/>`;
  };
  SETTIMANE.forEach((s, i) => {
    const x = pl + i * colW + (colW - bw) / 2;
    const yv = y(s[k]), yp = y(s[k] + s[kp]);
    svg += barra(x, y(0), yv, s[kp] <= 0, `fill="var(--accent)"`);
    if (s[kp] > 0) svg += barra(x + .75, s[k] > 0 ? yv - 2 : y(0), yp + .75, true, `fill="url(#hatch-l)" stroke="var(--accent)" stroke-width="1.5"`);
    const ogni = colW < 34 ? 3 : 2;
    if (((SETTIMANE.length - 1 - i) % ogni === 0 && Math.abs(i - SETTIMANE.findIndex((w) => w.corrente)) > 1) || s.corrente) {
      svg += `<text x="${x + bw / 2}" y="${H - 9}" text-anchor="middle" font-size="11" fill="${s.corrente ? "var(--text)" : "var(--muted)"}" font-weight="${s.corrente ? 650 : 400}">${s.corrente ? "Oggi" : `${s.inizio.getDate()} ${MESI[s.inizio.getMonth()]}`}</text>`;
    }
    svg += `<rect x="${pl + i * colW}" y="${pt}" width="${colW}" height="${H - pt - pb}" fill="transparent" data-i="${i}"/>`;
  });
  svg += `<line x1="${pl}" x2="${W - pr}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted)" stroke-width="1"/></svg>`;
  box.querySelector("svg")?.remove();
  box.insertAdjacentHTML("beforeend", svg);

  const tip = $("tip");
  const fmt = (v) => misura === "ore" ? durata(v * 3600) : `${num(v)} km`;
  box.querySelectorAll("rect[data-i]").forEach((el) => {
    const mostra = () => {
      const s = SETTIMANE[+el.dataset.i];
      const fine = addGiorni(s.inizio, 6);
      let righe = `<b>${s.inizio.getDate()} ${MESI[s.inizio.getMonth()]} – ${fine.getDate()} ${MESI[fine.getMonth()]}</b>`;
      if (!s.futura) righe += `<br>Svolto: ${fmt(s[k])} · ${s.n} att.`;
      if (s[kp] > 0 || s.futura) righe += `<br>In programma: ${fmt(s[kp])} · ${s.nP} all.`;
      tip.innerHTML = righe;
      const bx = el.getBBox(), scala = box.clientWidth / W;
      tip.style.left = `${Math.min(box.clientWidth - 90, Math.max(90, (bx.x + bx.width / 2) * scala))}px`;
      tip.style.top = `${y(s[k] + s[kp]) * scala - 8}px`;
      tip.style.opacity = 1;
    };
    el.addEventListener("mouseenter", mostra);
    el.addEventListener("touchstart", mostra, { passive: true });
    el.addEventListener("mouseleave", () => (tip.style.opacity = 0));
  });
}
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
  misura = b.dataset.m;
  document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  disegna();
}));
new ResizeObserver(() => disegna()).observe($("chart"));

// ------------------------------------------------------------ in programma
(() => {
  if (!PROG.length) { $("programma").innerHTML = `<div class="empty">Nessun allenamento in programma nelle prossime settimane.</div>`; return; }
  const gruppi = new Map();
  PROG.slice(0, 21).forEach((p) => {
    const lun = iso(lunedi(d(p.data)));
    if (!gruppi.has(lun)) gruppi.set(lun, []);
    gruppi.get(lun).push(p);
  });
  const corrente = iso(lunedi(OGGI));
  let html = "";
  for (const [lun, lista] of gruppi) {
    const tot = lista.reduce((s, x) => s + (x.sec || 0), 0);
    const titolo = lun === corrente ? "Questa settimana" : lun === iso(addGiorni(lunedi(OGGI), 7)) ? "Prossima settimana" : `Settimana del ${d(lun).getDate()} ${MESI[d(lun).getMonth()]}`;
    html += `<div class="week-group"><div class="week-title">${titolo}${tot ? ` · ${durata(tot)}` : ""}</div>`;
    for (const p of lista) {
      const x = d(p.data);
      html += `<div class="plan-item ${p.data === DATI.oggi ? "today" : ""}">
        <div class="day"><small>${GIORNI[x.getDay()]}</small><b>${x.getDate()}</b></div>
        <div class="row" style="min-width:0;flex-wrap:nowrap">${pallino(p.sport)}<span class="t">${esc(p.titolo)}</span></div>
        <div class="n">${[p.sec ? durata(p.sec) : "", p.km ? `${num(p.km)} km` : ""].filter(Boolean).join(" · ") || SPORT[p.sport]}</div>
      </div>`;
    }
    html += `</div>`;
  }
  $("programma").innerHTML = html;
})();

// ------------------------------------------------------------ per sport + previsioni
(() => {
  const da = addGiorni(lunedi(OGGI), -21);
  const per = {};
  ATT.filter((x) => d(x.data) >= da).forEach((x) => { per[x.sport] = (per[x.sport] || { sec: 0, n: 0 }); per[x.sport].sec += x.sec || 0; per[x.sport].n++; });
  const righe = Object.entries(per).sort((a, b) => b[1].sec - a[1].sec);
  const max = Math.max(1, ...righe.map((r) => r[1].sec));
  $("sport").innerHTML = righe.length ? righe.map(([s, v]) => `
    <div class="sport-row" title="${v.n} attività">
      <span class="row" style="flex-wrap:nowrap">${pallino(s)}${SPORT[s] || s}</span>
      <div class="track"><div class="fill" style="width:${(v.sec / max) * 100}%;background:var(--${s})"></div></div>
      <span class="v">${durata(v.sec)}</span>
    </div>`).join("") : `<div class="empty">Nessuna attività nelle ultime 4 settimane.</div>`;

  const prev = (DATI.forma || {}).previsioni || {};
  const voci = Object.entries(prev).filter(([, v]) => v);
  $("previsioni").innerHTML = voci.length ? voci.map(([k, v]) => `<div class="pred"><span>${k}</span><b>${orologio(v)}</b></div>`).join("") : "";
  if (voci.length) $("previsioni").insertAdjacentHTML("beforebegin", `<div class="label" style="margin-top:20px">Tempi previsti da Garmin</div>`);
  $("previsioni").style.marginTop = voci.length ? "8px" : "0";
})();

// ------------------------------------------------------------ tabella
(() => {
  const ultime = ATT.slice(0, 15);
  if (!ultime.length) { $("tabella").outerHTML = `<div class="empty">Nessuna attività registrata nelle ultime 12 settimane.</div>`; return; }
  $("tabella").innerHTML = `<thead><tr><th>Attività</th><th>Data</th><th class="r">Distanza</th><th class="r">Durata</th><th class="r">Passo / vel.</th><th class="r">FC media</th><th class="r">Training effect</th></tr></thead><tbody>${
    ultime.map((a) => `<tr>
      <td class="name"><span class="row" style="flex-wrap:nowrap">${pallino(a.sport)}${a.id ? `<a href="https://connect.garmin.com/modern/activity/${encodeURIComponent(a.id)}" target="_blank" rel="noopener">${esc(a.nome)}</a>` : esc(a.nome)}</span></td>
      <td>${dataBreve(a.data)} · ${a.data.slice(11, 16)}</td>
      <td class="r">${a.km ? `${num(a.km, 2)} km` : "–"}</td>
      <td class="r">${durata(a.sec)}</td>
      <td class="r">${ritmo(a)}</td>
      <td class="r">${a.fc ? `${Math.round(a.fc)} bpm` : "–"}</td>
      <td class="r">${a.te != null ? num(a.te) : "–"}</td>
    </tr>`).join("")}</tbody>`;
})();

// ------------------------------------------------------------ tema
$("tema").addEventListener("click", () => {
  const scuro = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = scuro ? "light" : "dark";
  try { localStorage.setItem("tema", document.documentElement.dataset.theme); } catch (e) {}
});
try { const t = localStorage.getItem("tema"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}

// ------------------------------------------------------------ dati di esempio (solo anteprima)
function demo() {
  const oggi = new Date(); const f = (n) => { const x = new Date(oggi); x.setDate(x.getDate() + n); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`; };
  const att = [];
  const tipi = [["corsa", "Corsa facile", 8, 2.9], ["bici", "Uscita in bici", 45, 7.5], ["corsa", "Ripetute", 10, 3.3], ["forza", "Forza", 0, 0], ["corsa", "Lungo", 18, 2.8], ["nuoto", "Nuoto", 2, 0.8]];
  for (let g = -83, i = 0; g <= 0; g += 1 + (i % 3 === 0 ? 1 : 0), i++) {
    const [s, n, km, v] = tipi[i % tipi.length]; const k = km ? km * (0.8 + ((i * 37) % 40) / 100) : 0;
    att.push({ id: null, nome: n, data: `${f(g)} 07:${String(10 + (i % 40)).padStart(2, "0")}`, sport: s, km: k ? +k.toFixed(2) : null, sec: k ? Math.round(k * 1000 / v) : 2700, fc: 130 + (i % 25), velocita: v || null, te: 2 + (i % 30) / 10 });
  }
  const prog = [[1, "Corsa facile 45'", "corsa", 2700, 8], [2, "Forza core", "forza", 1800, null], [3, "Soglia 3×10'", "corsa", 3600, 11], [5, "Lungo progressivo", "corsa", 6000, 18], [8, "Recupero", "corsa", 2400, 7], [9, "Ripetute 6×1000", "corsa", 3900, 12], [11, "Bici Z2", "bici", 5400, 45], [12, "Lungo 22 km", "corsa", 7200, 22], [16, "Corsa facile", "corsa", 2700, 8], [19, "Ritmo gara", "corsa", 4200, 14], [23, "Lungo 26 km", "corsa", 8400, 26], [26, "Fartlek", "corsa", 3300, 10], [30, "Lungo 30 km", "corsa", 9600, 30]];
  return {
    generato: "anteprima con dati di esempio", oggi: f(0), nome: "",
    attivita: att, programmati: prog.map(([g, t, s, sec, km]) => ({ data: f(g), titolo: t, sport: s, sec, km })),
    piani: [{ nome: "Maratona – sub 3:30", inizio: f(-56), fine: f(42) }],
    gara: { nome: "Maratona di esempio", data: f(42), km: 42.2 },
    forma: { vo2: 52.4, vo2bici: 49, stato: "PRODUCTIVE_1", acuto: 612, cronico: 540, previsioni: { "5 km": 1290, "10 km": 2700, "Mezza": 5950, "Maratona": 12500 } },
  };
}
</script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
