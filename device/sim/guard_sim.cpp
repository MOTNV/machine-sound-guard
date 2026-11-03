// 가상 ESP32: 펌웨어와 같은 판정 코드(device/firmware/app/src/guard)를 PC에서 돌린다.
// 표준 입력 = 16kHz 모노 16비트 PCM (tools/virtual_machine.py stream), 표준 출력 = 한 줄에 JSON 하나.
//
//   guard_sim features                    1초마다 {"rms":…, "features":[67개]}       (파이썬과 값 비교용)
//   guard_sim run [--calibrate 초]        1초마다 판정, 서버로 보낼 메시지(docs/contracts/device-log.md)를 출력
//                 [--windows]             1초마다 점수도 출력 {"kind":"window", …}
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <vector>

#include "guard.h"

using namespace guard;

static bool read_window(float* x) {
  static int16_t pcm[WINDOW];
  size_t got = fread(pcm, sizeof(int16_t), WINDOW, stdin);
  if (got < (size_t)WINDOW) return false;
  for (int i = 0; i < WINDOW; i++) x[i] = pcm[i] / 32767.0f;
  return true;
}

static void print_message(const Message& m) {
  switch (m.kind) {
    case Message::AnomalyStart:
      printf("{\"kind\":\"anomaly_start\",\"score\":%.3f}\n", m.score);
      break;
    case Message::AnomalyEnd:
      printf("{\"kind\":\"anomaly_end\",\"score\":%.3f,\"duration_s\":%d}\n", m.score, m.duration_s);
      break;
    case Message::Reading:
      printf("{\"kind\":\"reading\",\"window_s\":%d,\"state\":\"%s\",\"score_avg\":%.3f,\"score_max\":%.3f,\"anomaly_windows\":%d}\n",
             SUMMARY_EVERY, state_name(m.state), m.score_avg, m.score_max, m.anomaly_windows);
      break;
    default:
      break;
  }
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "사용: guard_sim features | run [--calibrate 초] [--windows]\n");
    return 2;
  }
  init();
  static float x[WINDOW];
  float f[N_FEATURES];
  if (!strcmp(argv[1], "features")) {
    while (read_window(x)) {
      features(x, f);
      printf("{\"rms\":%.7g,\"features\":[", rms(x));
      for (int j = 0; j < N_FEATURES; j++) printf(j ? ",%.7g" : "%.7g", f[j]);
      printf("]}\n");
    }
    return 0;
  }
  int calibrate_s = 0;
  bool windows = false;
  for (int i = 2; i < argc; i++) {
    if (!strcmp(argv[i], "--calibrate") && i + 1 < argc) calibrate_s = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--windows")) windows = true;
  }
  Model model;
  load_factory(model);
  printf("{\"kind\":\"model\",\"model\":\"%s\",\"threshold\":%.6g}\n", model.id, model.threshold);
  std::vector<float> calib;
  std::vector<float> work;
  Detector detector;
  Message out[2];
  while (read_window(x)) {
    float level = rms(x);
    features(x, f);
    if (calibrate_s > 0) {  // 현장 보정: 기계가 도는 동안의 소리만 모은다
      if (level >= OFF_RMS) calib.insert(calib.end(), f, f + N_FEATURES);
      int have = (int)(calib.size() / N_FEATURES);
      if (have < calibrate_s) {
        printf("{\"kind\":\"calibrating\",\"have_s\":%d,\"need_s\":%d}\n", have, calibrate_s);
        fflush(stdout);
        continue;
      }
      work.resize(have);
      calibrate(model, calib.data(), have, work.data());
      printf("{\"kind\":\"calibrated\",\"model\":\"%s\",\"threshold\":%.6g}\n", model.id, model.threshold);
      calibrate_s = 0;
      continue;
    }
    float s = score(model, f);
    if (windows) printf("{\"kind\":\"window\",\"rms\":%.5g,\"score\":%.5g}\n", level, s);
    int n = detector.update(level, s, out);
    for (int i = 0; i < n; i++) print_message(out[i]);
    fflush(stdout);
  }
  return 0;
}
