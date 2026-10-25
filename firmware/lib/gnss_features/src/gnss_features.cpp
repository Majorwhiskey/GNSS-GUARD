#include "gnss_features.h"

#include <cmath>
#include <cstring>

namespace gnss {

namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kDeg2Rad = kPi / 180.0;  // same expression as numpy.radians
constexpr double kEarthR = 6371000.0;

uint16_t u16(const uint8_t* p) { return p[0] | p[1] << 8; }
uint32_t u32(const uint8_t* p) { return p[0] | p[1] << 8 | p[2] << 16 | uint32_t(p[3]) << 24; }
int16_t i16(const uint8_t* p) { return int16_t(u16(p)); }
int32_t i32(const uint8_t* p) { return int32_t(u32(p)); }

double mean(const double* x, int n) {
  double s = 0;
  for (int i = 0; i < n; i++) s += x[i];
  return s / n;
}

// Population standard deviation (ddof = 0), as numpy's default.
double stddev(const double* x, int n, double m) {
  double s = 0;
  for (int i = 0; i < n; i++) s += (x[i] - m) * (x[i] - m);
  return std::sqrt(s / n);
}

}  // namespace

#define COL(name) {#name, offsetof(FeatureRow, name)}
const FeatureColumn kColumns[] = {
    COL(iTOW),          COL(fix),          COL(fix_ok),         COL(num_sv),         COL(lat),
    COL(lon),           COL(height),       COL(h_acc),          COL(v_acc),          COL(s_acc),
    COL(speed),         COL(vel_n),        COL(vel_e),          COL(vel_d),          COL(heading),
    COL(pdop),          COL(n_tracked),    COL(n_used),         COL(cno_mean),       COL(cno_std),
    COL(cno_max),       COL(cno_min),      COL(cno_top4),       COL(cno_elev_corr),  COL(prres_rms),
    COL(prres_maxabs),  COL(cno_delta_mean), COL(cno_delta_std), COL(ublox_spoof_state), COL(clk_bias),
    COL(clk_drift),     COL(t_acc),        COL(f_acc),          COL(noise),          COL(agc),
    COL(jam_ind),       COL(jam_state),    COL(clk_jump),       COL(pos_jump),       COL(heading_rate),
};
#undef COL
const int kNumColumns = sizeof(kColumns) / sizeof(kColumns[0]);

bool UbxParser::feed(uint8_t b) {
  switch (state_) {
    case kSync1:
      if (b == 0xB5) state_ = kSync2;
      return false;
    case kSync2:
      state_ = b == 0x62 ? kClass : b == 0xB5 ? kSync2 : kSync1;
      return false;
    case kClass:
      cls_ = b;
      ck_a_ = b;
      ck_b_ = ck_a_;
      state_ = kId;
      return false;
    case kId:
      id_ = b;
      break;
    case kLen1:
      len_ = b;
      break;
    case kLen2:
      len_ |= uint16_t(b) << 8;
      oversize_ = len_ > kMaxPayload;
      pos_ = 0;
      break;
    case kPayload:
      if (!oversize_) buf_[pos_] = b;
      pos_++;
      break;
    case kCkA:
      rx_ck_a_ = b;
      state_ = kCkB;
      return false;
    case kCkB:
      state_ = kSync1;
      return !oversize_ && rx_ck_a_ == ck_a_ && b == ck_b_;
  }
  // Bytes from id through payload are covered by the checksum.
  ck_a_ += b;
  ck_b_ += ck_a_;
  if (state_ == kId) {
    state_ = kLen1;
  } else if (state_ == kLen1) {
    state_ = kLen2;
  } else if (state_ == kLen2 || state_ == kPayload) {
    state_ = pos_ < len_ ? kPayload : kCkA;
  }
  return false;
}

FeatureExtractor::FeatureExtractor() {
  memset(&cur_, 0, sizeof(cur_));
  out_ = prev_ = cur_;
}

bool FeatureExtractor::onMessage(uint8_t cls, uint8_t id, const uint8_t* p, uint16_t len) {
  if (cls == 0x0A && id == 0x09) {  // MON-HW: no iTOW, belongs to the epoch in progress
    monHw(p, len);
    return false;
  }
  if (cls != 0x01 || len < 4) return false;
  bool closed = false;
  uint32_t itow = u32(p);
  if (!have_cur_ || itow != cur_itow_) {
    if (have_cur_) {
      closeEpoch();
      closed = true;
    }
    startEpoch(itow);
  }
  switch (id) {
    case 0x07: navPvt(p, len); break;
    case 0x35: navSat(p, len); break;
    case 0x03: navStatus(p, len); break;
    case 0x22: navClock(p, len); break;
  }
  return closed;
}

bool FeatureExtractor::flush() {
  if (!have_cur_) return false;
  closeEpoch();
  return true;
}

void FeatureExtractor::startEpoch(uint32_t itow) {
  for (int i = 0; i < kNumColumns; i++)
    *reinterpret_cast<double*>(reinterpret_cast<char*>(&cur_) + kColumns[i].offset) = NAN;
  cur_.iTOW = itow;
  cur_itow_ = itow;
  have_cur_ = true;
  // MON-HW values carry forward until the next MON-HW.
  if (hw_valid_) applyHw(cur_);
}

void FeatureExtractor::closeEpoch() {
  FeatureRow& r = cur_;
  if (have_prev_) {
    const FeatureRow& q = prev_;
    double dt = (r.iTOW - q.iTOW) / 1000.0;
    // Clock jump: bias change not explained by the reported drift (ns vs ns/s).
    r.clk_jump = (r.clk_bias - q.clk_bias) - q.clk_drift * dt;
    // Position jump: how far we moved vs how far the reported velocity says we should have.
    double dn = ((r.lat - q.lat) * kDeg2Rad) * kEarthR;
    double de = ((r.lon - q.lon) * kDeg2Rad) * kEarthR * std::cos(r.lat * kDeg2Rad);
    r.pos_jump = std::hypot(dn - q.vel_n * dt, de - q.vel_e * dt);
    // Python's % is a floor modulo; fmod truncates, so wrap negatives back into [0, 360).
    double m = std::fmod((r.heading - q.heading) + 180.0, 360.0);
    if (m < 0) m += 360.0;
    r.heading_rate = (m - 180.0) / dt;
  }
  out_ = r;
  prev_ = r;
  have_prev_ = true;
  have_cur_ = false;
}

void FeatureExtractor::navPvt(const uint8_t* p, uint16_t len) {
  if (len < 78) return;
  FeatureRow& r = cur_;
  r.fix = p[20];
  r.fix_ok = p[21] & 0x01;
  r.num_sv = p[23];
  r.lon = i32(p + 24) * 1e-7;
  r.lat = i32(p + 28) * 1e-7;
  r.height = i32(p + 32) / 1000.0;
  r.h_acc = u32(p + 40) / 1000.0;
  r.v_acc = u32(p + 44) / 1000.0;
  r.vel_n = i32(p + 48) / 1000.0;
  r.vel_e = i32(p + 52) / 1000.0;
  r.vel_d = i32(p + 56) / 1000.0;
  r.speed = i32(p + 60) / 1000.0;
  r.heading = i32(p + 64) * 1e-5;
  r.s_acc = u32(p + 68) / 1000.0;
  r.pdop = u16(p + 76) * 0.01;
}

void FeatureExtractor::navSat(const uint8_t* p, uint16_t len) {
  int num_svs = p[5];
  if (len < 8 + 12 * num_svs) return;
  FeatureRow& r = cur_;
  int n = 0, n_used = 0;
  for (int i = 0; i < num_svs && n < kMaxSats; i++) {
    const uint8_t* s = p + 8 + 12 * i;
    if (s[2] == 0) continue;  // C/N0 0: not tracked
    key_[n] = uint16_t(s[0]) << 8 | s[1];
    cno_[n] = s[2];
    elev_[n] = int8_t(s[3]);
    if ((u32(s + 8) >> 3) & 0x01) pr_[n_used++] = i16(s + 6) * 0.1;  // svUsed
    n++;
  }
  r.n_tracked = n;
  if (n > 0) {
    r.n_used = n_used;
    double m = mean(cno_, n);
    r.cno_mean = m;
    r.cno_std = stddev(cno_, n, m);
    r.cno_max = r.cno_min = cno_[0];
    for (int i = 1; i < n; i++) {
      if (cno_[i] > r.cno_max) r.cno_max = cno_[i];
      if (cno_[i] < r.cno_min) r.cno_min = cno_[i];
    }
    // Mean of the 4 strongest (all of them if fewer): partial selection sort on a copy.
    memcpy(tmp_, cno_, n * sizeof(double));
    int k = n < 4 ? n : 4;
    for (int i = 0; i < k; i++)
      for (int j = i + 1; j < n; j++)
        if (tmp_[j] > tmp_[i]) {
          double t = tmp_[i];
          tmp_[i] = tmp_[j];
          tmp_[j] = t;
        }
    r.cno_top4 = mean(tmp_, k);
    // Real satellites: higher in the sky -> stronger. A single-antenna spoofer breaks this.
    double me = mean(elev_, n);
    if (n > 2 && r.cno_std > 0 && stddev(elev_, n, me) > 0) {
      double sxy = 0, sxx = 0, syy = 0;
      for (int i = 0; i < n; i++) {
        sxy += (cno_[i] - m) * (elev_[i] - me);
        sxx += (cno_[i] - m) * (cno_[i] - m);
        syy += (elev_[i] - me) * (elev_[i] - me);
      }
      double c = sxy / std::sqrt(sxx * syy);
      r.cno_elev_corr = c > 1 ? 1 : c < -1 ? -1 : c;
    }
    if (n_used > 0) {
      double ss = 0, mx = 0;
      for (int i = 0; i < n_used; i++) {
        ss += pr_[i] * pr_[i];
        if (std::fabs(pr_[i]) > mx) mx = std::fabs(pr_[i]);
      }
      r.prres_rms = std::sqrt(ss / n_used);
      r.prres_maxabs = mx;
    }
    // Spoofer power changes hit every satellite at once: big mean shift, small spread.
    int nd = 0;
    for (int i = 0; i < n; i++)
      for (int j = 0; j < prev_n_; j++)
        if (prev_key_[j] == key_[i]) {
          tmp_[nd++] = cno_[i] - prev_cno_[j];
          break;
        }
    if (nd >= 3) {
      double dm = mean(tmp_, nd);
      r.cno_delta_mean = dm;
      r.cno_delta_std = stddev(tmp_, nd, dm);
    }
  }
  memcpy(prev_key_, key_, n * sizeof(uint16_t));
  memcpy(prev_cno_, cno_, n * sizeof(double));
  prev_n_ = n;
}

void FeatureExtractor::navStatus(const uint8_t* p, uint16_t len) {
  if (len < 8) return;
  cur_.ublox_spoof_state = (p[7] >> 3) & 0x03;
}

void FeatureExtractor::navClock(const uint8_t* p, uint16_t len) {
  if (len < 20) return;
  cur_.clk_bias = i32(p + 4);
  cur_.clk_drift = i32(p + 8);
  cur_.t_acc = u32(p + 12);
  cur_.f_acc = u32(p + 16);
}

void FeatureExtractor::monHw(const uint8_t* p, uint16_t len) {
  if (len < 46) return;
  hw_noise_ = u16(p + 16);
  hw_agc_ = u16(p + 18);
  hw_jam_state_ = (p[22] >> 2) & 0x03;
  hw_jam_ind_ = p[45];
  hw_valid_ = true;
  if (have_cur_) applyHw(cur_);
}

void FeatureExtractor::applyHw(FeatureRow& r) const {
  r.noise = hw_noise_;
  r.agc = hw_agc_;
  r.jam_ind = hw_jam_ind_;
  r.jam_state = hw_jam_state_;
}

}  // namespace gnss
