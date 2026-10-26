"""Mostra un riepilogo dei tuoi dati Garmin di oggi.

La prima volta chiede email, password (ed eventuale codice MFA),
poi salva i token in %USERPROFILE%\\.garminconnect e non li chiede piu.
"""

from datetime import date
from getpass import getpass
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

TOKENSTORE = str(Path("~/.garminconnect").expanduser())


def accedi() -> Garmin:
    # Prova con i token salvati
    try:
        garmin = Garmin()
        garmin.login(TOKENSTORE)
        return garmin
    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
        print("Primo accesso: inserisci le credenziali Garmin Connect.")

    email = input("Email: ").strip()
    password = getpass("Password (non viene mostrata mentre scrivi): ")
    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Codice MFA: ").strip(),
    )
    garmin.login(TOKENSTORE)
    print("Accesso riuscito, token salvati.")
    return garmin


def main() -> None:
    garmin = accedi()
    oggi = date.today().isoformat()

    riepilogo = garmin.get_user_summary(oggi) or {}
    print(f"\nRiepilogo di oggi ({oggi})")
    print(f"Passi     : {riepilogo.get('totalSteps') or 0}")
    print(f"Calorie   : {riepilogo.get('totalKilocalories') or 0:.0f} kcal")
    print(f"Distanza  : {(riepilogo.get('totalDistanceMeters') or 0) / 1000:.2f} km")
    print(f"FC riposo : {riepilogo.get('restingHeartRate') or 'n/d'} bpm")

    input("\nPremi Invio per chiudere...")


if __name__ == "__main__":
    main()
