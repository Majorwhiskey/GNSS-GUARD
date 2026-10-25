// Native build of the firmware feature library: .ubx file in, feature CSV out.
// Built and compared against tools/features.py by tests/test_firmware_parity.py.
#include <cmath>
#include <cstdio>

#include "gnss_features.h"

static void printRow(const gnss::FeatureRow& r) {
  for (int i = 0; i < gnss::kNumColumns; i++) {
    double v = gnss::column(r, i);
    if (i) putchar(',');
    if (!std::isnan(v)) printf("%.17g", v);
  }
  putchar('\n');
}

int main(int argc, char** argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s <log.ubx>\n", argv[0]);
    return 2;
  }
  FILE* f = fopen(argv[1], "rb");
  if (!f) {
    perror(argv[1]);
    return 1;
  }
  for (int i = 0; i < gnss::kNumColumns; i++) printf(i ? ",%s" : "%s", gnss::kColumns[i].name);
  putchar('\n');

  static gnss::UbxParser parser;
  static gnss::FeatureExtractor fx;
  int c;
  while ((c = fgetc(f)) != EOF)
    if (parser.feed(uint8_t(c)) && fx.onMessage(parser.cls(), parser.id(), parser.payload(), parser.length()))
      printRow(fx.row());
  if (fx.flush()) printRow(fx.row());
  fclose(f);
  return 0;
}
