# 07:45 verdict — 2026-06-17

Route 12 excludes operator 7's TRIP_019 (see reconciliation rules); it does not affect the route-12 row,
which is TRIP_015 on V-10.

| route | name | verdict | note |
|---|---|---|---|
| 11 | Borivali → BKC | **CALL_DRIVER** | TRIP_014 (V-06) has not moved from Borivali Stn since 06:46 — 59 min past scheduled departure, 8 riders booked. Not a "running slow" case. |
| 17 | Vashi → Worli | **NO_VERDICT** | TRIP_017 (V-05) — total GPS silence since 07:27, 18 min before as-of, 16 riders booked (most of any live trip). Can't trust a number this stale; won't guess. |
| 12 | Mulund → Andheri E | HOLD *(SOP)* | TRIP_015 (V-10) reported on-time per the contractual rev. C reconciliation rule. Raw telemetry actually shows **+10.2 min** behind schedule — see decision record. |
| 14 | Kandivali → Lower Parel | HOLD | TRIP_016 (V-04) +0.8 min — on schedule, despite a 90-min clock-label glitch on this vehicle (see decision record). |
| 9 | Thane → Powai | HOLD | TRIP_013 (V-11) +0.5 min — on schedule, 99% along route. |
| 21 | Ghatkopar → BKC | HOLD | TRIP_018 (V-03) −0.1 min — on schedule. (TRIP_019/V-09 excluded, operator 7.) |

## Worry-order

1. **Route 17** — highest-ridership live trip (16 riders) with zero live signal for 18 minutes right at
   the moment ops needs an answer. Could be a dead zone, a dead device, or a genuinely stalled bus — we
   can't tell which from here, and that's exactly the problem. Chase this first: a phone call to the
   driver resolves it in one step and either clears the route or catches the same failure mode as route
   11 before it costs another 8+ riders their morning.
2. **Route 11** — already a confirmed operational failure (bus hasn't left the origin), but it's a known
   problem with a clear next action (call driver/depot), not an open question. Lower urgency than route
   17 only because there's nothing left to *find out* — the fix is the same either way, dispatch a
   replacement or find out what's holding the vehicle.
3. **Route 12** — real drift (+10.2 min) is being suppressed in the published figure by design. Not an
   emergency, but Priya should know the real number going into the standup so she isn't blindsided if
   someone asks about it, and so the "on-time" figure doesn't quietly become the thing ops manages
   toward instead of the thing riders actually experience.

Routes 9, 14, 21: clean, no action.
