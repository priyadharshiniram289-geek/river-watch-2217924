"""
River Watch - build the history summary ONCE (Task 1, "compute it once and store it").

Source : Open-Meteo Flood API (GloFAS v4 river discharge, daily, m3/s)
         https://flood-api.open-meteo.com/v1/flood
         Data CC BY 4.0 - "Flood data by Open-Meteo.com (GloFAS, Copernicus Emergency Management Service)"
Period : 1 Jan 2016 - 31 Dec 2025 (ten full years)
Output : history_summary.json  (stored in the repo and read by index.html)
         history_summary.csv   (same numbers, for the written answers / Excel check)
         history_daily_<town>.csv (raw daily values, kept so you can re-check p99 in Excel)

Run on your own laptop:   python build_history_summary.py
No API key is needed. Only the Python standard library is used.
"""
import csv
import json
import urllib.request
from datetime import date, datetime

START, END = "2016-01-01", "2025-12-31"
FIRST_WINTER, LAST_WINTER = 2016, 2024  # winters 2016/17 ... 2024/25 (Flood Plan rule 8)

# Coordinates = a point ON the named river in each town (check each one in Task 1).
TOWNS = [
    # town,               county,      river,        lat,      lon
    ("Clonmel",            "Tipperary", "Suir",       52.3500, -7.7030),
    ("Fermoy",             "Cork",      "Blackwater", 52.1360, -8.2760),
    ("Mallow",             "Cork",      "Blackwater", 52.1300, -8.6420),
    ("Bandon",             "Cork",      "Bandon",     51.7450, -8.7400),
    ("Enniscorthy",        "Wexford",   "Slaney",     52.5000, -6.5600),
    ("Ennis",              "Clare",     "Fergus",     52.8430, -8.9800),
    ("Athlone",            "Westmeath", "Shannon",    53.4230, -7.9440),
    ("Carrick-on-Shannon", "Leitrim",   "Shannon",    53.9450, -8.0920),
]


def percentile(values, p):
    """Linear interpolation - identical to Excel PERCENTILE.INC and numpy's default."""
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def cell_centre(x):
    """Snap to the centre of the 0.05-degree GloFAS square that contains x."""
    return round(((x + 1e-9) // 0.05) * 0.05 + 0.025, 3)


def choose_cell(lat, lon):
    """Test the 3x3 squares around the town (about 7 km each way) over one year
    and keep the one with the biggest average flow = the main river."""
    clat, clon = cell_centre(lat), cell_centre(lon)
    cands = [(round(clat + a * 0.05, 3), round(clon + b * 0.05, 3))
             for a in (-1, 0, 1) for b in (-1, 0, 1)]
    url = (
        "https://flood-api.open-meteo.com/v1/flood"
        f"?latitude={','.join(str(c[0]) for c in cands)}"
        f"&longitude={','.join(str(c[1]) for c in cands)}"
        "&daily=river_discharge&start_date=2024-01-01&end_date=2024-12-31&cell_selection=nearest"
    )
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    if isinstance(data, dict):
        data = [data]
    scored = []
    for (clat_i, clon_i), d in zip(cands, data):
        q = [v for v in d["daily"]["river_discharge"] if v is not None]
        scored.append((sum(q) / len(q) if q else 0.0, clat_i, clon_i))
    scored.sort(reverse=True)
    return scored  # best first: (mean_2024, lat, lon)


def fetch(lat, lon):
    url = (
        "https://flood-api.open-meteo.com/v1/flood"
        f"?latitude={lat}&longitude={lon}&daily=river_discharge"
        f"&start_date={START}&end_date={END}&cell_selection=nearest"
    )
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    days = data["daily"]["time"]
    flows = data["daily"]["river_discharge"]
    pairs = [(datetime.strptime(d, "%Y-%m-%d").date(), q) for d, q in zip(days, flows) if q is not None]
    return pairs, data.get("latitude"), data.get("longitude"), url


def winter_of(d):
    """Winter label = year it starts (1 Oct - 31 Mar). Returns None outside winter."""
    if d.month >= 10:
        return d.year
    if d.month <= 3:
        return d.year - 1
    return None


def count_events(pairs, p99):
    """An event = a run of consecutive winter days with flow >= p99 (rule 8)."""
    per_winter = {w: 0 for w in range(FIRST_WINTER, LAST_WINTER + 1)}
    prev_high_day = None
    for d, q in pairs:
        w = winter_of(d)
        if w is None or w not in per_winter or q < p99:
            continue
        if prev_high_day is None or (d - prev_high_day).days != 1:
            per_winter[w] += 1          # a new run starts
        prev_high_day = d
    return per_winter


def summarise(town, county, river, lat, lon, pairs, glat, glon, url):
    flows = [q for _, q in pairs]
    p95, p99 = percentile(flows, 95), percentile(flows, 99)
    ev = count_events(pairs, p99)
    winters = list(range(FIRST_WINTER, LAST_WINTER + 1))
    first4 = sum(ev[w] for w in winters[:4])   # 2016/17 - 2019/20
    last4 = sum(ev[w] for w in winters[-4:])   # 2021/22 - 2024/25
    peak_day, peak_q = max(pairs, key=lambda x: x[1])
    return {
        "town": town, "county": county, "river": river,
        "lat_requested": lat, "lon_requested": lon,
        "lat_grid": glat, "lon_grid": glon,
        "period": f"{START} to {END}", "days": len(flows),
        "mean_m3s": round(sum(flows) / len(flows), 2),
        "median_m3s": round(percentile(flows, 50), 2),
        "p95_m3s": round(p95, 2), "p99_m3s": round(p99, 2),
        "max_m3s": round(peak_q, 2), "max_date": peak_day.isoformat(),
        "winter_events_total": sum(ev.values()),
        "winter_events_by_winter": {f"{w}/{str(w + 1)[2:]}": ev[w] for w in winters},
        "events_first4_winters": first4, "events_last4_winters": last4,
        "source": "Open-Meteo Flood API, GloFAS v4 river_discharge (CC BY 4.0)",
        "source_url": url,
        "computed_on": date.today().isoformat(),
    }


def main():
    rows = []
    search_log = []
    for town, county, river, lat, lon in TOWNS:
        scored = choose_cell(lat, lon)
        for rank, (m, a, b) in enumerate(scored):
            search_log.append({"town": town, "rank": rank + 1, "lat": a, "lon": b,
                               "mean_2024_m3s": round(m, 2), "chosen": rank == 0})
        lat, lon = scored[0][1], scored[0][2]
        print(f"{town:20s} chosen square {lat}, {lon} (2024 mean {scored[0][0]:.1f}; "
              f"next best {scored[1][0]:.1f})")
        pairs, glat, glon, url = fetch(lat, lon)
        with open(f"history_daily_{town}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "river_discharge_m3s"])
            w.writerows((d.isoformat(), q) for d, q in pairs)
        row = summarise(town, county, river, lat, lon, pairs, glat, glon, url)
        rows.append(row)
        print(f"{town:20s} mean {row['mean_m3s']:8.1f}  p95 {row['p95_m3s']:8.1f}  "
              f"p99 {row['p99_m3s']:8.1f}  events {row['winter_events_total']:3d}  "
              f"(first4 {row['events_first4_winters']}, last4 {row['events_last4_winters']})")

    with open("history_summary.json", "w") as f:
        json.dump(rows, f, indent=2)
    flat = ["town", "county", "river", "lat_requested", "lon_requested", "lat_grid", "lon_grid",
            "days", "mean_m3s", "median_m3s", "p95_m3s", "p99_m3s", "max_m3s", "max_date",
            "winter_events_total", "events_first4_winters", "events_last4_winters"]
    with open("history_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open("cell_search_log.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["town", "rank", "lat", "lon", "mean_2024_m3s", "chosen"])
        w.writeheader()
        w.writerows(search_log)
    best = max(rows, key=lambda r: (r["winter_events_total"], r["p99_m3s"]))
    print(f"\nMost winter high-flow events: {best['town']} ({best['winter_events_total']})")


if __name__ == "__main__":
    main()
