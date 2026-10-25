// Per-epoch features from u-blox UBX messages, mirroring tools/features.py.
//
// Plain C++ with no Arduino dependency, so the same code runs on the ESP32 and in the
// native parity test (tests/test_firmware_parity.py). Any change to a feature must be
// made here, in tools/features.py and in docs/FEATURES.md together.
//
// Differences from the Python reference, all deliberate:
// - Streaming: an epoch is emitted when the next one starts (or on flush()), so derived
//   features use the previous emitted row. Python sorts rows by iTOW first; the two agree
//   unless iTOW goes backwards (week rollover).
// - Epochs are opened by NAV-class messages (all start with iTOW); Python uses any parsed
//   message with an iTOW attribute. Same result for the configured message set.
// - pyubx2 rounds scaled fields to 12 decimals; this code does not (< 1e-12 difference).
#pragma once

#include <cstddef>
#include <cstdint>

namespace gnss {

// NAV-SAT carries up to 255 satellites; M8 receivers report well under 80.
constexpr int kMaxSats = 80;
constexpr uint16_t kMaxPayload = 8 + 12 * kMaxSats;

// One row per navigation epoch. Every field is a double, NaN when not available,
// with the units documented in docs/FEATURES.md.
struct FeatureRow {
  double iTOW;
  double fix, fix_ok, num_sv, lat, lon, height, h_acc, v_acc, s_acc, speed, vel_n, vel_e, vel_d, heading, pdop;
  double n_tracked, n_used, cno_mean, cno_std, cno_max, cno_min, cno_top4, cno_elev_corr, prres_rms,
      prres_maxabs, cno_delta_mean, cno_delta_std;
  double ublox_spoof_state, clk_bias, clk_drift, t_acc, f_acc, noise, agc, jam_ind, jam_state;
  double clk_jump, pos_jump, heading_rate;
};

struct FeatureColumn {
  const char* name;
  size_t offset;
};
extern const FeatureColumn kColumns[];
extern const int kNumColumns;

inline double column(const FeatureRow& r, int i) {
  return *reinterpret_cast<const double*>(reinterpret_cast<const char*>(&r) + kColumns[i].offset);
}

// Byte-at-a-time UBX framer. Messages with a bad checksum or a payload longer than
// kMaxPayload are dropped.
class UbxParser {
 public:
  // True when b completes a valid message, readable until the next call.
  bool feed(uint8_t b);
  uint8_t cls() const { return cls_; }
  uint8_t id() const { return id_; }
  const uint8_t* payload() const { return buf_; }
  uint16_t length() const { return len_; }

 private:
  enum State { kSync1, kSync2, kClass, kId, kLen1, kLen2, kPayload, kCkA, kCkB };
  State state_ = kSync1;
  uint8_t cls_ = 0, id_ = 0, ck_a_ = 0, ck_b_ = 0, rx_ck_a_ = 0;
  uint16_t len_ = 0, pos_ = 0;
  bool oversize_ = false;
  uint8_t buf_[kMaxPayload];
};

class FeatureExtractor {
 public:
  FeatureExtractor();
  // Feed one UBX message. True if it closed the previous epoch, which is then in row().
  bool onMessage(uint8_t cls, uint8_t id, const uint8_t* p, uint16_t len);
  // End of stream: close the current epoch. False if there is none.
  bool flush();
  const FeatureRow& row() const { return out_; }

 private:
  void startEpoch(uint32_t itow);
  void closeEpoch();
  void navPvt(const uint8_t* p, uint16_t len);
  void navSat(const uint8_t* p, uint16_t len);
  void navStatus(const uint8_t* p, uint16_t len);
  void navClock(const uint8_t* p, uint16_t len);
  void monHw(const uint8_t* p, uint16_t len);
  void applyHw(FeatureRow& r) const;

  FeatureRow cur_, out_, prev_;
  bool have_cur_ = false, have_prev_ = false;
  uint32_t cur_itow_ = 0;

  bool hw_valid_ = false;
  double hw_noise_ = 0, hw_agc_ = 0, hw_jam_ind_ = 0, hw_jam_state_ = 0;

  // C/N0 of the previous NAV-SAT, keyed by gnssId << 8 | svId, for cno_delta_*.
  uint16_t prev_key_[kMaxSats];
  double prev_cno_[kMaxSats];
  int prev_n_ = 0;
  // Scratch for the current NAV-SAT, kept off the stack.
  uint16_t key_[kMaxSats];
  double cno_[kMaxSats], elev_[kMaxSats], pr_[kMaxSats], tmp_[kMaxSats];
};

}  // namespace gnss
