"""Turn a .ubx log into one feature row per navigation epoch (1 Hz).

Usage: python tools/features.py data/raw/*.ubx   ->  writes data/features/<same name>.csv
"""
import math
import os
import sys

import numpy as np
import pandas as pd
from pyubx2 import UBX_PROTOCOL, UBXReader

def sat_features(msg):
    sats = []
    for i in range(1, msg.numSvs + 1):
        g = lambda k: getattr(msg, f"{k}_{i:02d}")
        if g("cno") > 0:
            sats.append(((g("gnssId"), g("svId")), g("cno"), g("elev"), g("prRes"), g("svUsed")))
    f = {"n_tracked": len(sats)}
    if not sats:
        return f, {}
    cno = np.array([s[1] for s in sats], float)
    elev = np.array([s[2] for s in sats], float)
    used = [s for s in sats if s[4]]
    pr = np.array([s[3] for s in used], float)
    f.update(
        n_used=len(used),
        cno_mean=cno.mean(),
        cno_std=cno.std(),
        cno_max=cno.max(),
        cno_min=cno.min(),
        cno_top4=np.sort(cno)[-4:].mean(),
        # Real satellites: higher in the sky -> stronger. A single-antenna spoofer breaks this.
        cno_elev_corr=np.corrcoef(cno, elev)[0, 1] if len(sats) > 2 and cno.std() > 0 and elev.std() > 0 else np.nan,
        prres_rms=math.sqrt((pr**2).mean()) if len(pr) else np.nan,
        prres_maxabs=np.abs(pr).max() if len(pr) else np.nan,
    )
    return f, {s[0]: s[1] for s in sats}


def extract(path):
    rows, cur = {}, None
    prev_cno = {}
    hw_last = {}
    with open(path, "rb") as fh:
        for _, msg in UBXReader(fh, protfilter=UBX_PROTOCOL, quitonerror=0):
            if msg is None:
                continue
            ident = msg.identity
            if ident == "MON-HW":  # no timestamp, attach to the current epoch
                hw_last = dict(noise=msg.noisePerMS, agc=msg.agcCnt, jam_ind=msg.jamInd, jam_state=msg.jammingState)
                if cur is not None:
                    rows[cur].update(hw_last)
                continue
            if not hasattr(msg, "iTOW"):
                continue
            if msg.iTOW != cur:  # new epoch
                cur = msg.iTOW
                rows.setdefault(cur, {"iTOW": cur, **hw_last})
            r = rows[cur]
            if ident == "NAV-PVT":
                r.update(fix=msg.fixType, fix_ok=msg.gnssFixOk, num_sv=msg.numSV, lat=msg.lat, lon=msg.lon,
                         height=msg.height / 1000, h_acc=msg.hAcc / 1000, v_acc=msg.vAcc / 1000,
                         s_acc=msg.sAcc / 1000, speed=msg.gSpeed / 1000, vel_n=msg.velN / 1000,
                         vel_e=msg.velE / 1000, vel_d=msg.velD / 1000, heading=msg.headMot, pdop=msg.pDOP)
            elif ident == "NAV-SAT":
                f, cno_now = sat_features(msg)
                r.update(f)
                common = set(cno_now) & set(prev_cno)
                if len(common) >= 3:
                    d = np.array([cno_now[k] - prev_cno[k] for k in common], float)
                    # Spoofer power changes hit every satellite at once: big mean shift, small spread.
                    r["cno_delta_mean"], r["cno_delta_std"] = d.mean(), d.std()
                prev_cno = cno_now
            elif ident == "NAV-STATUS":
                r["ublox_spoof_state"] = msg.spoofDetState
            elif ident == "NAV-CLOCK":
                r.update(clk_bias=msg.clkB, clk_drift=msg.clkD, t_acc=msg.tAcc, f_acc=msg.fAcc)

    df = pd.DataFrame(sorted(rows.values(), key=lambda r: r["iTOW"]))
    if df.empty:
        return df
    dt = df["iTOW"].diff() / 1000
    # Clock jump: bias change not explained by the reported drift (ns vs ns/s).
    if "clk_bias" in df:
        df["clk_jump"] = df["clk_bias"].diff() - df["clk_drift"].shift() * dt
    if "lat" in df:
        lat0 = np.radians(df["lat"])
        dn = np.radians(df["lat"].diff()) * 6371000
        de = np.radians(df["lon"].diff()) * 6371000 * np.cos(lat0)
        # Position jump: how far we moved vs how far the reported velocity says we should have.
        df["pos_jump"] = np.hypot(dn - df["vel_n"].shift() * dt, de - df["vel_e"].shift() * dt)
        df["heading_rate"] = ((df["heading"].diff() + 180) % 360 - 180) / dt
    return df


if __name__ == "__main__":
    os.makedirs("data/features", exist_ok=True)
    for path in sys.argv[1:]:
        df = extract(path)
        out = os.path.join("data/features", os.path.basename(path).rsplit(".", 1)[0] + ".csv")
        df.to_csv(out, index=False)
        print(f"{path}: {len(df)} epochs, {len(df.columns)} columns -> {out}")
