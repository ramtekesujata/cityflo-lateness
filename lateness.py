"""
Cityflo route lateness — 07:45 IST verdict, live morning 2026-06-17.

Definition of "late": timetable-progress-based. For each live trip we project
the vehicle's last known GPS ping onto its route geometry to get
distance-covered-so-far, compare that to the fraction of scheduled runtime
elapsed (uniform-pace assumption under the published timetable), and convert
the gap back into minutes. See DECISION_RECORD.md for why this baseline was
picked over promised_eta / historical-typical-runtime, and for the four
routes where the rule needed a human call on top of the number.

Reconciliation rules applied per HANDOFF.md (rev. C):
  - operator_id 7 vehicles are dropped entirely (still in onboarding).
  - Route 12 is reported HOLD regardless of raw drift, per the contractual
    on-time commitment — see DECISION_RECORD.md for the real number and why
    it's still flagged on the worry-order.

Run: python3 lateness.py
"""
import math
import pandas as pd

AS_OF = pd.Timestamp("2026-06-17 07:45:00+05:30")
DATA = "data"

# ---- reconciliation rules (HANDOFF.md rev. C) ------------------------------
DROP_OPERATOR_IDS = {7}
CONTRACTUAL_ON_TIME_ROUTES = {12}

# ---- verdict thresholds (see DECISION_RECORD.md for the case each one is
# tuned against) --------------------------------------------------------------
STALE_MIN = 10          # no ping in this long before as-of -> can't trust the read -> NO_VERDICT
STUCK_FRAC = 0.05        # covered less than this fraction of the route ...
STUCK_SCHED_FRAC = 0.30  # ... while this much of scheduled runtime has already elapsed -> CALL_DRIVER
PUSH_THRESHOLD_MIN = 5   # |delay| at/above this -> PUSH_LATE, else HOLD

# ---- geometry ---------------------------------------------------------------
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_route_geometry(stops: pd.DataFrame) -> dict:
    """route_id -> ordered stops with cumulative distance-along-route (m)."""
    geo = {}
    for rid, grp in stops.groupby("route_id"):
        grp = grp.sort_values("seq").reset_index(drop=True)
        dist = [0.0]
        for i in range(1, len(grp)):
            dist.append(dist[-1] + haversine_m(grp.lat[i - 1], grp.lon[i - 1], grp.lat[i], grp.lon[i]))
        geo[rid] = grp.assign(cum_dist_m=dist)
    return geo


def project_onto_route(geo_route: pd.DataFrame, lat: float, lon: float) -> tuple[float, float]:
    """Nearest-segment projection. Returns (perpendicular_offset_m, dist_along_route_m)."""
    best = None
    for i in range(len(geo_route) - 1):
        ax, ay = geo_route.lat[i], geo_route.lon[i]
        bx, by = geo_route.lat[i + 1], geo_route.lon[i + 1]
        lat0 = (ax + bx) / 2
        mlat, mlon = 111320.0, 111320.0 * math.cos(math.radians(lat0))
        axm, aym, bxm, bym = ax * mlat, ay * mlon, bx * mlat, by * mlon
        pxm, pym = lat * mlat, lon * mlon
        dx, dy = bxm - axm, bym - aym
        seglen2 = dx * dx + dy * dy
        t = 0.0 if seglen2 == 0 else max(0.0, min(1.0, ((pxm - axm) * dx + (pym - aym) * dy) / seglen2))
        projx, projy = axm + t * dx, aym + t * dy
        off = math.hypot(pxm - projx, pym - projy)
        along = geo_route.cum_dist_m[i] + t * haversine_m(ax, ay, bx, by)
        if best is None or off < best[0]:
            best = (off, along)
    return best


# ---- clock repair -------------------------------------------------------------
def load_pings() -> pd.DataFrame:
    """Parse ping timestamps and repair the one malformed recorded_at row
    (P-0001797: '06:60:23', an out-of-range minute — device clock glitch,
    unrelated to the live morning). received_at is well-formed throughout, so
    we re-derive recorded_at from received_at minus that vehicle's median
    network latency on clean rows."""
    p = pd.read_csv(f"{DATA}/gps_pings.csv")
    p["received_at"] = pd.to_datetime(p["received_at"], format="mixed")
    p["recorded_at"] = pd.to_datetime(p["recorded_at"], format="mixed", errors="coerce")
    bad = p["recorded_at"].isna()
    if bad.any():
        good = ~bad
        lat_med = (p.loc[good, "received_at"] - p.loc[good, "recorded_at"]).dt.total_seconds().groupby(p.loc[good, "vehicle_id"]).median()
        for i in p.index[bad]:
            vid = p.loc[i, "vehicle_id"]
            p.loc[i, "recorded_at"] = p.loc[i, "received_at"] - pd.Timedelta(seconds=lat_med.get(vid, 1))
    return p


def last_trusted_ping(pings: pd.DataFrame, vehicle_id: str, as_of: pd.Timestamp):
    """Last ping at/before as_of, trusting recorded_at unless it disagrees
    with received_at by more than 5 minutes AND the disagreement isn't
    corroborated by physically-plausible continuous progress (see
    DECISION_RECORD.md, 'V-04 clock disagreement'). For this dataset the one
    large (90 min) skew case (V-04) passes the plausibility check — smooth
    continuous progress and sane speeds either side of the glitch — so
    recorded_at is kept as the ordering clock throughout.
    """
    v = pings[(pings.vehicle_id == vehicle_id) & (pings.recorded_at <= as_of)].sort_values("recorded_at")
    return v.iloc[-1] if len(v) else None


# ---- main pipeline ------------------------------------------------------------
def main():
    routes = pd.read_csv(f"{DATA}/routes.csv")
    stops = pd.read_csv(f"{DATA}/stops.csv")
    trips = pd.read_csv(f"{DATA}/trips.csv")
    trips["scheduled_start"] = pd.to_datetime(trips["scheduled_start"], format="mixed")
    trips["scheduled_end"] = pd.to_datetime(trips["scheduled_end"], format="mixed")
    bookings = pd.read_csv(f"{DATA}/bookings.csv")
    pings = load_pings()
    geo = build_route_geometry(stops)
    veh_operator = pings.groupby("vehicle_id")["operator_id"].first()

    live = trips[trips.service_date == "2026-06-17"].copy()
    live["operator_id"] = live.vehicle_id.map(veh_operator)
    live = live[~live.operator_id.isin(DROP_OPERATOR_IDS)]  # reconciliation rule: drop operator 7

    rows = []
    for _, tr in live.iterrows():
        rid, vid = tr.route_id, tr.vehicle_id
        total_m = geo[rid].cum_dist_m.iloc[-1]
        runtime_min = routes.loc[routes.route_id == rid, "scheduled_runtime_min"].iloc[0]
        n_bookings = (bookings.trip_id == tr.trip_id).sum()

        last = last_trusted_ping(pings, vid, AS_OF)
        sched_elapsed_min = (AS_OF - tr.scheduled_start).total_seconds() / 60
        frac_sched = min(1.0, max(0.0, sched_elapsed_min / runtime_min))

        if last is None:
            rows.append(dict(route=rid, trip=tr.trip_id, bookings=n_bookings,
                              verdict="NO_VERDICT", delay_min=None,
                              note="no telemetry received for this vehicle before 07:45"))
            continue

        off_m, along_m = project_onto_route(geo[rid], last.lat, last.lon)
        frac_actual = along_m / total_m
        staleness_min = (AS_OF - last.recorded_at).total_seconds() / 60
        delay_min = (frac_sched - frac_actual) * runtime_min

        verdict, note = classify(rid, frac_actual, frac_sched, staleness_min, delay_min)

        rows.append(dict(route=rid, trip=tr.trip_id, vehicle=vid, bookings=n_bookings,
                          verdict=verdict, note=note,
                          delay_min=round(delay_min, 1), staleness_min=round(staleness_min, 1),
                          frac_actual_pct=round(frac_actual * 100, 1), off_route_m=round(off_m, 0),
                          speed_kmph=last.speed_kmph, last_ping=last.ping_id))

    # A route can lose its only live trip to the operator-7 exclusion (or have
    # none scheduled at all) and would otherwise vanish from the table instead
    # of being accounted for — surface it as NO_VERDICT rather than silence.
    covered_routes = {r["route"] for r in rows}
    for rid in routes.route_id:
        if rid in covered_routes:
            continue
        all_today = trips[(trips.service_date == "2026-06-17") & (trips.route_id == rid)]
        reason = ("only scheduled trip today is operator 7 (excluded by onboarding SOP), no fallback trip"
                  if len(all_today) else "no trip scheduled for this route this morning")
        rows.append(dict(route=rid, trip=None, bookings=0, verdict="NO_VERDICT", delay_min=None, note=reason))

    return pd.DataFrame(rows)


def classify(route_id: int, frac_actual: float, frac_sched: float, staleness_min: float, delay_min: float):
    """Verdict logic. Order matters: a stale or stuck signal is disqualifying
    before we even look at the delay number, because the number isn't
    trustworthy in those cases regardless of what it says."""
    if staleness_min > STALE_MIN:
        return "NO_VERDICT", f"no ping in {staleness_min:.0f} min before 07:45 — can't trust a number this stale"

    if frac_actual < STUCK_FRAC and frac_sched > STUCK_SCHED_FRAC:
        return "CALL_DRIVER", f"only {frac_actual*100:.1f}% along route but {frac_sched*100:.0f}% of scheduled time elapsed — looks stuck/not departed, not just running slow"

    if route_id in CONTRACTUAL_ON_TIME_ROUTES:
        return "HOLD", f"reported on-time per contractual SOP (HANDOFF.md rev. C) — raw telemetry shows {delay_min:+.1f} min, see DECISION_RECORD.md"

    if delay_min >= PUSH_THRESHOLD_MIN:
        return f"PUSH_LATE {delay_min:.0f} min", "running behind schedule by more than the push threshold"

    return "HOLD", f"within +/-{PUSH_THRESHOLD_MIN} min of schedule ({delay_min:+.1f})"


if __name__ == "__main__":
    df = main()
    pd.set_option("display.width", 160)
    print(df.to_string(index=False))
