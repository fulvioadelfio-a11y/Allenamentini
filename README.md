# Allenamentini

Dashboard personale degli allenamenti, generata dai dati di Garmin Connect con la libreria
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect).

## Script

| File | Cosa fa |
|---|---|
| `garmin_sito.py` | Scarica attività, allenamenti in programma, piano, gara obiettivo e metriche di forma, poi crea il sito in `%USERPROFILE%\Allenamentini\index.html` e lo apre nel browser. |
| `allenamentini.html` | Modello della pagina: `garmin_sito.py` lo riempie con i dati (deve stare nella stessa cartella). |
| `garmin_oggi.py` | Riepilogo veloce della giornata nel terminale (passi, calorie, distanza, FC a riposo). |

## Installazione (Windows)

1. Installa Python 3.12 o successivo da <https://www.python.org/downloads/>.
2. Nel terminale: `py -m pip install garminconnect`
3. Avvia: `py garmin_sito.py`

In alternativa, fai doppio clic su `Aggiorna_Allenamentini.bat` (deve stare nella stessa cartella di `garmin_sito.py`).

Al primo avvio vengono chiesti email, password ed eventuale codice MFA; i token vengono salvati
in `%USERPROFILE%\.garminconnect` e riutilizzati dopo. Rilancia lo script per aggiornare i dati.

## Privacy

Nel repository non ci sono dati personali né credenziali: `dati.json`, la cartella del sito
generato e i token sono esclusi da `.gitignore`.

## Sito online sempre aggiornato

Il workflow `.github/workflows/aggiorna.yml` gira su GitHub Actions ogni 3 ore (e a richiesta
da *Actions → Aggiorna Allenamentini → Run workflow*): scarica i dati, pubblica la dashboard su
GitHub Pages e salva `dati.json` sul ramo `dati`.

Indirizzo: <https://fulvioadelfio-a11y.github.io/Allenamentini/>

Configurazione (una volta sola):

1. *Settings → Secrets and variables → Actions → New repository secret*: nome `GARMINTOKENS`,
   valore = contenuto di `%USERPROFILE%\.garminconnect\garmin_tokens.json`.
2. (Facoltativo) secret `GARMIN_PERSONAL_API_KEY` con la chiave della Garmin Personal API ufficiale:
   abilita la sezione Recupero (FC a riposo, Body Battery, stress).
3. *Settings → Pages → Source*: **GitHub Actions**.
4. *Actions → Aggiorna Allenamentini → Run workflow* per il primo aggiornamento.

Garmin rinnova i token a ogni accesso; il workflow conserva l'ultima versione, cifrata, nella
cache di Actions. Se l'aggiornamento fallisce con "Token Garmin non validi", rilancia
`garmin_sito.py` sul PC e copia di nuovo `garmin_tokens.json` nel secret.

Attenzione: con GitHub Pages gratuito il repository deve essere pubblico, quindi la dashboard
e `dati.json` sono visibili a chiunque abbia il link.
