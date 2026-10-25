# Data collection

Goal: at least 20 hours of clean data across varied conditions, plus a
labelled set of benign degradations. Clean data trains the anomaly model;
degradations are what keep the false-alarm rate honest.

## Recording a session

```bash
.venv/bin/python tools/log.py --port <port> --scenario <scenario> --notes "<where, how mounted, weather>"
```

`<port>` is `/dev/ttyUSB0` on Linux and `/dev/cu.usbserial-*` on macOS, see
[SETUP.md](SETUP.md#find-the-serial-port). With the receiver plugged straight
into USB instead of the bridge, use its `/dev/cu.usbmodem*` port and add
`--configure`; see [HARDWARE.md](HARDWARE.md#direct-usb-logging-no-bridge).

Each session writes two files to `data/raw/`:

- `YYYYMMDD_HHMMSS_<scenario>.ubx`: raw receiver output, never edited.
- `YYYYMMDD_HHMMSS_<scenario>.json`: scenario name, notes, start time.

Stop with Ctrl+C. Short sessions are fine; many varied sessions beat one
long one.

## Scenario names

### Clean (label: normal)

| Scenario | Description | Target |
|---|---|---|
| `clean_static` | Antenna fixed outdoors or on a balcony, open sky | 5 h |
| `clean_walk` | Walking with the antenna on a backpack or held up | 3 h |
| `clean_bike` | Two-wheeler, module fixed to the vehicle | 4 h |
| `clean_car` | Car, module fixed on the dashboard, antenna on roof or dash | 6 h |
| `clean_night` | Any of the above at night (different ionosphere, traffic) | 2 h |

### Benign degradation (label: normal, but hard)

| Scenario | Description |
|---|---|
| `degraded_foliage` | Under dense tree cover |
| `degraded_urban` | Between tall buildings |
| `degraded_flyover` | Passing under flyovers and bridges |
| `degraded_indoor` | Moving from outdoors to indoors and back |
| `degraded_blocked` | Antenna covered by a hand or foil for 10–30 s, then uncovered |
| `degraded_cold_start` | Power-on with no fix, until stable 3D fix |

For `degraded_blocked`, write the approximate times of each blockage in the
notes (for example "blocked 60–80 s, 140–170 s"), so they can be labelled.

### Attack (imported only)

| Scenario | Source |
|---|---|
| `attack_texbat_ds<N>` | TEXBAT scenario N, processed through GNSS-SDR |
| `attack_oakbat_<name>` | OAKBAT scenario |
| `attack_synth_<type>` | Synthetic injection into a clean log, see DATASETS.md |

## Safety and legality

- Never transmit on GNSS frequencies. No jammers, no SDR playback, not even
  into a shielded box.
- Record while riding or driving only with the setup secured and someone else
  handling the laptop. Do not interact with the logger while driving.
- Logs contain your exact location history. Keep `data/raw/` out of git and
  out of public uploads; publish only processed features, or trimmed tracks
  with the start and end of each session removed.

## First session: confirm what the receiver sends

Do this once, before collecting anything for training. Use scenario
`clean_static` with the antenna outdoors and a clear sky view.

| Step | Action | Pass |
|---|---|---|
| 1 | Flash the bridge, run the logger | `logging to ...` printed, no serial errors |
| 2 | Wait up to 5 min for a fix | `fix=3` and `sv` of 8 or more |
| 3 | Read the `msgs:` line after 2 min | NAV-PVT, NAV-SAT, NAV-STATUS, NAV-CLOCK, MON-HW all increasing |
| 4 | **RXM-RAWX check** (below) | Present or absent, either result is recorded |
| 5 | Stop after about 10 min, run `tools/features.py` on the log | CSV produced, no exceptions |

### RXM-RAWX check

The bridge requests RXM-RAWX at boot, but the firmware does not report whether
the receiver accepted it. Decide from what actually arrives:

```bash
.venv/bin/python - data/raw/<session>.ubx <<'PY'
import sys, collections
from pyubx2 import UBXReader, UBX_PROTOCOL
with open(sys.argv[1], "rb") as f:
    c = collections.Counter(m.identity for _, m in UBXReader(f, protfilter=UBX_PROTOCOL, quitonerror=0) if m)
print(dict(c))
print("RXM-RAWX:", "PRESENT" if c.get("RXM-RAWX") else "ABSENT")
PY
```

| Result | Consequence |
|---|---|
| RXM-RAWX count about equal to NAV-PVT count | Doppler and carrier-phase features become possible; add them to FEATURES.md first |
| RXM-RAWX absent after 10 min with a fix | Treat as unsupported. NAV-level features only; the optional NEO-M8T / ZED-F9P is the upgrade path |

Record the outcome in the Hardware facts section of CLAUDE.md and in
[HARDWARE.md](HARDWARE.md).

## Checklist before each session

1. Antenna connected, clear sky view at the start.
2. ESP32 bridge flashed and the logger shows `fix=3` within a few minutes.
3. `msgs:` line shows NAV-PVT, NAV-SAT, NAV-STATUS, NAV-CLOCK, MON-HW
   increasing.
4. For vehicle sessions, antenna and boards secured, placement noted.
5. Laptop on power or charged, at least 1 GB free disk, sleep disabled
   (`caffeinate -i` on macOS) so the logger is not suspended.
6. Scenario name matches the tables above; notes say where, how mounted,
   weather.

## During and after a session

- Watch the 5 s status line; a frozen `msgs:` count means the serial link
  dropped, stop and restart (a new file starts).
- Stop with Ctrl+C and confirm `saved ...ubx` is printed.
- Check the `.ubx` is non-empty and a `.json` sits beside it.
- Extra detail goes in the `.json` notes field (edit the sidecar only; never
  the `.ubx`), for example blockage times for `degraded_blocked`.
- Run `tools/features.py` on the new log, then `tools/split.py
  data/features/*.csv` to assign it to a split; commit `data/splits.json`.
- Do not commit anything from `data/raw/` or `data/features/`.

## Suggested order

Cheap, low-risk sessions first, so problems show up early.

| Order | Scenario | Length | Why this order |
|---|---|---|---|
| 1 | `clean_static` | 10 min | First-session checks above |
| 2 | `degraded_cold_start` | until stable 3D fix | Easy, shows time-to-first-fix |
| 3 | `degraded_blocked` | 5 min, 3 blockages | Controlled, known label times |
| 4 | `clean_static` | 1–2 h | Bulk clean data, can run while doing other work |
| 5 | `clean_walk` | 30–60 min | First moving data, exercises velocity and heading features |
| 6 | `degraded_foliage`, `degraded_urban`, `degraded_indoor` | 15–30 min each | Hard negatives |
| 7 | `clean_bike`, `clean_car`, `degraded_flyover` | as planned | Needs a secured mount and a second person |
| 8 | `clean_night` | repeat of any above | Different ionosphere and traffic |

Progress against the 20 h target:

| Group | Target | Done |
|---|---|---|
| clean_static | 5 h | 0 |
| clean_walk | 3 h | 0 |
| clean_bike | 4 h | 0 |
| clean_car | 6 h | 0 |
| clean_night | 2 h | 0 |
