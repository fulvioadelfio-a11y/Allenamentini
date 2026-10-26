# Allenamentini

Dashboard personale degli allenamenti, generata dai dati di Garmin Connect con la libreria
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect).

## Script

| File | Cosa fa |
|---|---|
| `garmin_sito.py` | Scarica attività, allenamenti in programma, piano, gara obiettivo e metriche di forma, poi crea il sito in `%USERPROFILE%\Allenamentini\index.html` e lo apre nel browser. |
| `garmin_oggi.py` | Riepilogo veloce della giornata nel terminale (passi, calorie, distanza, FC a riposo). |

## Installazione (Windows)

1. Installa Python 3.12 o successivo da <https://www.python.org/downloads/>.
2. Nel terminale: `py -m pip install garminconnect`
3. Avvia: `py garmin_sito.py`

Al primo avvio vengono chiesti email, password ed eventuale codice MFA; i token vengono salvati
in `%USERPROFILE%\.garminconnect` e riutilizzati dopo. Rilancia lo script per aggiornare i dati.

## Privacy

Nel repository non ci sono dati personali né credenziali: `dati.json`, la cartella del sito
generato e i token sono esclusi da `.gitignore`.
