"""Synthetic UBX logs shared by the tests."""
import numpy as np
from pyubx2 import GET, UBXMessage

N_EPOCHS = 10
T0 = 100_000  # iTOW of first epoch, ms
ELEVS = [15, 25, 40, 55, 70, 85]
CLEAN_CNOS = [28, 32, 37, 41, 44, 47]


def nav_sat(itow, cnos, elevs):
    kw = dict(iTOW=itow, version=1, numSvs=len(cnos))
    for i, (c, e) in enumerate(zip(cnos, elevs), 1):
        kw.update({f"gnssId_{i:02d}": 0, f"svId_{i:02d}": i, f"cno_{i:02d}": c, f"elev_{i:02d}": e,
                   f"azim_{i:02d}": i * 50, f"prRes_{i:02d}": 1.0, f"svUsed_{i:02d}": 1})
    return UBXMessage("NAV", "NAV-SAT", GET, **kw).serialize()


def write_log(path, n_epochs=N_EPOCHS, clock_jump_at=None, spoof_from=None, noise_seed=None):
    """Receiver walking north at 1.112 m/s. noise_seed adds small measurement jitter, so
    thresholds fitted on the log are not degenerate."""
    rng = np.random.default_rng(noise_seed) if noise_seed is not None else None
    out = bytearray()
    for e in range(n_epochs):
        t = T0 + e * 1000
        lat = 12.97 + e * 1e-5 + (rng.normal(0, 0.3) / 111_195 if rng else 0)
        out += UBXMessage("NAV", "NAV-PVT", GET, iTOW=t, fixType=3, gnssFixOk=1, numSV=6,
                          lat=lat, lon=77.59, height=900_000, hAcc=2500, vAcc=4000,
                          sAcc=300, gSpeed=1112, velN=1112, velE=0, headMot=0, pDOP=1.5).serialize()
        if spoof_from is not None and e >= spoof_from:
            cnos = [48, 47, 48, 49, 48, 47]  # uniform and strong, uncorrelated with elevation
        else:
            cnos = [c + (int(rng.integers(-1, 2)) if rng else 0) for c in CLEAN_CNOS]
        out += nav_sat(t, cnos, ELEVS)
        out += UBXMessage("NAV", "NAV-STATUS", GET, iTOW=t, gpsFix=3, spoofDetState=1).serialize()
        bias = 1000 + e * 50 + (5000 if clock_jump_at is not None and e >= clock_jump_at else 0)
        bias += round(rng.normal(0, 2)) if rng else 0
        out += UBXMessage("NAV", "NAV-CLOCK", GET, iTOW=t, clkB=bias, clkD=50, tAcc=20, fAcc=5).serialize()
        out += UBXMessage("MON", "MON-HW", GET, noisePerMS=90 + (int(rng.integers(-5, 6)) if rng else 0),
                          agcCnt=4000, jamInd=10 + (int(rng.integers(-5, 6)) if rng else 0),
                          jammingState=1).serialize()
    path.write_bytes(bytes(out))
    return path
