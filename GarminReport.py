"""
GarminReport.py
───────────────
Gera um relatório dos últimos N dias com todas as métricas do Garmin Connect:
  - Resumo diário (calorias, passos, distância, andares, intensidade)
  - Frequência cardíaca (repouso, mín, máx)
  - Sono (total, profundo, leve, REM)
  - VO2 Max
  - Nível de stress
  - Body Battery
  - Atividades do período (com calorias)

Uso:
  python GarminReport.py          # últimos 7 dias (padrão)
  python GarminReport.py 14       # últimos 14 dias
  python GarminReport.py 30       # últimos 30 dias
"""

import base64
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://connectapi.garmin.com"
SESS_HEADERS = {
    "User-Agent": "GCM-iOS-5.7.2.1",
    "NK": "NT",
    "origin": "https://connect.garmin.com",
}

# ─── Auth ────────────────────────────────────────────────────────────────────

def load_token() -> dict:
    raw = os.environ.get("GARTH_TOKEN")
    if not raw:
        raise RuntimeError("GARTH_TOKEN not found in .env")
    decoded = json.loads(base64.b64decode(raw).decode())
    return decoded[1] if isinstance(decoded, list) else decoded["oauth2"]


def make_session(oauth2: dict) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(SESS_HEADERS)
    sess.headers["Authorization"] = f"Bearer {oauth2['access_token']}"
    return sess

# ─── API calls ───────────────────────────────────────────────────────────────

def api_get(sess, path, params=None):
    try:
        r = sess.get(f"{BASE}{path}", params=params, timeout=15)
        if r.status_code == 204:
            return {}
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def get_profile(sess):
    return api_get(sess, "/userprofile-service/socialProfile")


def get_daily_summary(sess, display_name, d):
    return api_get(sess, f"/usersummary-service/usersummary/daily/{display_name}",
                   {"calendarDate": d})


def get_heart_rate(sess, d):
    return api_get(sess, "/wellness-service/wellness/dailyHeartRate", {"date": d})


def get_sleep(sess, d):
    return api_get(sess, "/wellness-service/wellness/dailySleepData", {"date": d})


def get_stress(sess, d):
    return api_get(sess, "/wellness-service/wellness/dailyStress", {"date": d})


def get_body_battery(sess, d):
    # returns a list of readings; we take min/max
    data = api_get(sess, "/wellness-service/wellness/bodyBattery/reports/daily",
                   {"startDate": d, "endDate": d})
    if isinstance(data, list) and data:
        return data[0]
    return {}


def get_vo2max(sess, display_name):
    """VO2 Max — tries multiple endpoints."""
    # Try fitness stats
    data = api_get(sess, f"/fitnessstats-service/fitnessStats/{display_name}")
    if data:
        return data
    # Try maxmet metrics
    data = api_get(sess, f"/metrics-service/metrics/maxmet/latest/{display_name}")
    return data


def get_activities(sess, start_date, end_date, limit=50):
    data = api_get(sess,
        "/activitylist-service/activities/search/activities",
        {"startDate": start_date, "endDate": end_date, "start": 0, "limit": limit},
    )
    return data if isinstance(data, list) else []


def get_hrv(sess, d):
    return api_get(sess, "/hrv-service/hrv", {"date": d})


# ─── Formatters ──────────────────────────────────────────────────────────────

def fv(v, unit="", decimals=None):
    """Format a value; N/A if None."""
    if v is None:
        return "N/A"
    if decimals is not None:
        return f"{v:.{decimals}f}{unit}"
    return f"{v}{unit}"


def fmt_seconds(s):
    if s is None:
        return "N/A"
    h, rem = divmod(int(s), 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"


def fmt_duration(s):
    s = int(s)
    return f"{s // 60}m{s % 60:02d}s"


SEP = "─" * 60

# ─── Report ──────────────────────────────────────────────────────────────────

def build_daily_rows(sess, display_name, days):
    """Returns a list of dicts, one per day, with all metrics."""
    rows = []
    today = date.today()
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()

        summary  = get_daily_summary(sess, display_name, d)
        hr_data  = get_heart_rate(sess, d)
        sleep    = get_sleep(sess, d)
        stress   = get_stress(sess, d)
        bb       = get_body_battery(sess, d)
        hrv      = get_hrv(sess, d)

        sleep_dto = (sleep.get("dailySleepDTO") or {}) if sleep else {}
        hrv_sum   = (hrv.get("hrvSummary") or {}) if hrv else {}

        row = {
            "date":             d,
            # calories
            "total_kcal":       summary.get("totalKilocalories"),
            "active_kcal":      summary.get("activeKilocalories"),
            "bmr_kcal":         summary.get("bmrKilocalories"),
            # movement
            "steps":            summary.get("totalSteps"),
            "distance_m":       summary.get("totalDistanceMeters"),
            "floors_up":        summary.get("floorsAscended"),
            "active_min":       summary.get("moderateIntensityMinutes"),
            "vigorous_min":     summary.get("vigorousIntensityMinutes"),
            # heart rate
            "hr_resting":       hr_data.get("restingHeartRate"),
            "hr_min":           hr_data.get("minHeartRate"),
            "hr_max":           hr_data.get("maxHeartRate"),
            # sleep
            "sleep_total_s":    sleep_dto.get("sleepTimeSeconds"),
            "sleep_deep_s":     sleep_dto.get("deepSleepSeconds"),
            "sleep_light_s":    sleep_dto.get("lightSleepSeconds"),
            "sleep_rem_s":      sleep_dto.get("remSleepSeconds"),
            "sleep_awake_s":    sleep_dto.get("awakeSleepSeconds"),
            "sleep_score":      sleep_dto.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(sleep_dto.get("sleepScores"), dict) else None,
            # stress
            "stress_avg":       stress.get("avgStressLevel") if stress else None,
            "stress_max":       stress.get("maxStressLevel") if stress else None,
            # body battery
            "bb_high":          bb.get("charged"),
            "bb_low":           bb.get("drained"),
            # HRV
            "hrv_weekly_avg":   hrv_sum.get("weeklyAvg"),
            "hrv_last_night":   hrv_sum.get("lastNight"),
            "hrv_5min_high":    hrv_sum.get("highHrv5MinReadingTime"),
        }
        rows.append(row)
    return rows


def print_daily_table(rows):
    print(SEP)
    print(f"{'DATA':<12} {'KCAL':>6} {'ATIV':>6} {'PASS':>6} {'DIST':>7} "
          f"{'HR':>4} {'HRmx':>5} {'SONO':>8} {'STRESS':>6} {'BB':>4} {'HRV':>4}")
    print(SEP)
    for r in rows:
        dist = f"{r['distance_m']/1000:.1f}km" if r["distance_m"] else "N/A"
        sleep = fmt_seconds(r["sleep_total_s"]) if r["sleep_total_s"] else "N/A"
        print(
            f"{r['date']:<12} "
            f"{fv(r['total_kcal']):>6} "
            f"{fv(r['active_kcal']):>6} "
            f"{fv(r['steps']):>6} "
            f"{dist:>7} "
            f"{fv(r['hr_resting']):>4} "
            f"{fv(r['hr_max']):>5} "
            f"{sleep:>8} "
            f"{fv(r['stress_avg']):>6} "
            f"{fv(r['bb_high']):>4} "
            f"{fv(r['hrv_last_night']):>4}"
        )
    print(SEP)


def print_daily_detail(rows):
    for r in rows:
        print(f"\n{'━'*60}")
        print(f"  {r['date']}")
        print(f"{'━'*60}")

        print(f"  CALORIAS")
        print(f"    Total        : {fv(r['total_kcal'], ' kcal')}")
        print(f"    Ativas       : {fv(r['active_kcal'], ' kcal')}")
        print(f"    BMR          : {fv(r['bmr_kcal'], ' kcal')}")

        print(f"  MOVIMENTO")
        print(f"    Passos       : {fv(r['steps'])}")
        dist = f"{r['distance_m']/1000:.2f} km" if r["distance_m"] else "N/A"
        print(f"    Distância    : {dist}")
        print(f"    Andares      : {fv(r['floors_up'])}")
        mod = (r["active_min"] or 0) + (r["vigorous_min"] or 0) * 2
        print(f"    Min. ativos  : {fv(r['active_min'])} mod + {fv(r['vigorous_min'])} vig = {mod} pts")

        print(f"  FREQUÊNCIA CARDÍACA")
        print(f"    Repouso      : {fv(r['hr_resting'], ' bpm')}")
        print(f"    Mínima       : {fv(r['hr_min'], ' bpm')}")
        print(f"    Máxima       : {fv(r['hr_max'], ' bpm')}")

        print(f"  SONO")
        print(f"    Total        : {fmt_seconds(r['sleep_total_s'])}")
        print(f"    Profundo     : {fmt_seconds(r['sleep_deep_s'])}")
        print(f"    Leve         : {fmt_seconds(r['sleep_light_s'])}")
        print(f"    REM          : {fmt_seconds(r['sleep_rem_s'])}")
        print(f"    Acordado     : {fmt_seconds(r['sleep_awake_s'])}")
        print(f"    Score        : {fv(r['sleep_score'])}")

        print(f"  STRESS")
        print(f"    Médio        : {fv(r['stress_avg'])}")
        print(f"    Máximo       : {fv(r['stress_max'])}")

        print(f"  BODY BATTERY")
        print(f"    Máximo (dia) : {fv(r['bb_high'])}")
        print(f"    Mínimo (dia) : {fv(r['bb_low'])}")

        print(f"  HRV")
        print(f"    Última noite : {fv(r['hrv_last_night'], ' ms')}")
        print(f"    Média semanal: {fv(r['hrv_weekly_avg'], ' ms')}")


def print_activities(activities):
    print(f"\n{SEP}")
    print(f"ATIVIDADES DO PERÍODO ({len(activities)} encontradas)")
    print(SEP)
    if not activities:
        print("  Nenhuma atividade encontrada.")
        return
    for act in activities:
        sport    = (act.get("activityType") or {}).get("typeKey", "?")
        name     = act.get("activityName", "?")
        start_t  = act.get("startTimeLocal", "?")
        dur      = int(act.get("duration") or 0)
        dist     = (act.get("distance") or 0) / 1000
        calories = int(act.get("calories") or 0)
        hr_avg   = act.get("averageHR")
        hr_max   = act.get("maxHR")
        aerobic  = act.get("aerobicTrainingEffect")
        vo2      = act.get("vO2MaxValue")

        hr_str  = f"HR {hr_avg:.0f}/{hr_max:.0f}" if hr_avg and hr_max else ""
        vo2_str = f"  VO2 {vo2:.1f}" if vo2 else ""
        ae_str  = f"  TE {aerobic:.1f}" if aerobic else ""

        print(
            f"  [{start_t}]  {sport:<18}  {dist:>5.2f} km  "
            f"{fmt_duration(dur):>8}  {calories:>4} kcal  "
            f"{hr_str:<14}{vo2_str}{ae_str}  \"{name}\""
        )
    print(SEP)


def print_vo2(sess, display_name):
    print(f"\n{SEP}")
    print("VO2 MAX & FITNESS")
    print(SEP)
    data = get_vo2max(sess, display_name)
    if not data:
        print("  (não disponível — dispositivo pode não suportar VO2 Max)")
        print(SEP)
        return
    # campos podem variar por dispositivo
    vo2     = (data.get("vo2Max") or data.get("generic", {}).get("vo2Max")
               or data.get("latestVo2Max"))
    fa      = (data.get("fitnessAge") or data.get("generic", {}).get("fitnessAge")
               or data.get("latestFitnessAge"))
    vo2_run = data.get("vo2MaxPreciseRunning")
    vo2_cyc = data.get("vo2MaxPreciseCycling")
    print(f"  VO2 Max           : {fv(vo2, ' ml/kg/min')}")
    print(f"  VO2 Max (corrida) : {fv(vo2_run, ' ml/kg/min')}")
    print(f"  VO2 Max (ciclismo): {fv(vo2_cyc, ' ml/kg/min')}")
    print(f"  Fitness Age       : {fv(fa, ' anos')}")
    # dump raw if all N/A  
    if vo2 is None and fa is None:
        print(f"  (raw) {json.dumps(data)[:200]}")
    print(SEP)


# ─── JSON export ─────────────────────────────────────────────────────────────

def export_json(rows, activities, output_file="garmin_report.json"):
    payload = {
        "generated_at": date.today().isoformat(),
        "daily": rows,
        "activities": [
            {
                "date":       a.get("startTimeLocal", "")[:10],
                "start":      a.get("startTimeLocal"),
                "type":       (a.get("activityType") or {}).get("typeKey"),
                "name":       a.get("activityName"),
                "duration_s": a.get("duration"),
                "distance_m": a.get("distance"),
                "calories":   a.get("calories"),
                "hr_avg":     a.get("averageHR"),
                "hr_max":     a.get("maxHR"),
                "vo2_max":    a.get("vO2MaxValue"),
                "training_effect": a.get("aerobicTrainingEffect"),
            }
            for a in activities
        ],
    }
    Path(output_file).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n  [JSON salvo em: {output_file}]")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7

    oauth2 = load_token()
    sess   = make_session(oauth2)

    print(SEP)
    print(f"  GARMIN REPORT  —  últimos {days} dias")
    print(SEP)

    profile      = api_get(sess, "/userprofile-service/socialProfile")
    display_name = profile.get("displayName", "")
    print(f"  Usuário : {profile.get('fullName', 'N/A')}  ({display_name[:8]}…)")
    print(SEP)

    start_date = (date.today() - timedelta(days=days - 1)).isoformat()
    end_date   = date.today().isoformat()

    print(f"\nColetando dados de {start_date} até {end_date}…")
    rows = build_daily_rows(sess, display_name, days)

    # ── tabela resumo
    print(f"\n{SEP}")
    print("RESUMO DIÁRIO")
    print("Legenda: KCAL=total  ATIV=ativas  PASS=passos  DIST=distância")
    print("         HR=repouso  HRmx=max  SONO=total  STRESS  BB=bodyBattery  HRV")
    print_daily_table(rows)

    # ── detalhe por dia
    print(f"\n{SEP}")
    print("DETALHE POR DIA")
    print_daily_detail(rows)

    # ── atividades
    activities = get_activities(sess, start_date, end_date)
    print_activities(activities)

    # ── VO2 Max
    print_vo2(sess, display_name)

    # ── exportar JSON
    export_json(rows, activities, f"garmin_report_{days}d.json")

    print(f"\n  Relatório concluído.\n")


if __name__ == "__main__":
    main()
