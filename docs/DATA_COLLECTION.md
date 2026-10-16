# Data collection

Goal: at least 20 hours of clean data across varied conditions, plus a
labelled set of benign degradations. Clean data trains the anomaly model;
degradations are what keep the false-alarm rate honest.

## Recording a session

```bash
.venv/bin/python tools/log.py --port /dev/ttyUSB0 --scenario <scenario> --notes "<where, how mounted, weather>"
```

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

## Checklist before each session

1. Antenna connected, clear sky view at the start.
2. ESP32 bridge flashed and the logger shows `fix=3` within a few minutes.
3. `msgs:` line shows NAV-PVT, NAV-SAT, NAV-STATUS, NAV-CLOCK, MON-HW
   increasing.
4. For vehicle sessions, module rigidly mounted and orientation noted.
