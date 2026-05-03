import json
import requests
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ZONE_FILE = BASE_DIR / "zone-waktu-solat.json"

API_BASE_URL = "https://api.waktusolat.app"


def load_zones():
    with open(ZONE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def find_zone_by_daerah(daerah_name: str):
    zones = load_zones()
    search_text = daerah_name.lower().strip()

    matches = []

    for zone in zones:
        daerah = zone["daerah"].lower()
        negeri = zone["negeri"].lower()
        jakim_code = zone["jakimCode"].lower()

        if (
            search_text in daerah
            or search_text in negeri
            or search_text == jakim_code
        ):
            matches.append(zone)

    if not matches:
        raise ValueError(f"ugh, what is {daerah_name}")

    if len(matches) > 1:
        match_text = "\n".join(
            f"-{zone['negeri']} - {zone['daerah']}"
            for zone in matches
        )

        raise ValueError(
            f"ughh, which part of '{daerah_name}'. "
            f"be more specific.\n\n{match_text}"
        )

    return matches[0]


def format_time_12h(time_str: str):
    return datetime.strptime(time_str, "%H:%M:%S").strftime("%I:%M %p")


def format_waktu_solat(data: dict, zone_info: dict):
    prayer = data["prayerTime"]

    return f"""
Waktu Solat

Negeri {zone_info["negeri"]} 
Daerah: {zone_info["daerah"]}

Date: {prayer["day"]}, {prayer["date"]}
Hijri: {prayer["hijri"]}

Subuh:   {format_time_12h(prayer["fajr"])}
Syuruk:  {format_time_12h(prayer["syuruk"])}
Zohor:   {format_time_12h(prayer["dhuhr"])}
Asar:    {format_time_12h(prayer["asr"])}
Maghrib: {format_time_12h(prayer["maghrib"])}
Isyak:   {format_time_12h(prayer["isha"])}
""".strip()


def get_waktu_solat_by_daerah(daerah: str, day: int, month: int, year: int):
    zone_info = find_zone_by_daerah(daerah)
    zone_code = zone_info["jakimCode"]

    url = f"{API_BASE_URL}/solat/{zone_code}/{day}"
    params = {
        "year": year,
        "month": month
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    return format_waktu_solat(data, zone_info)
