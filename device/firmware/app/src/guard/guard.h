// 판정 코드 (ESP32 펌웨어와 PC용 가상 ESP32가 같이 쓴다). 파이썬 기준 구현: model/features.py, model/kmeans.py, model/detector.py
// 아두이노 전용 기능을 쓰지 않는다 (PC에서도 g++로 빌드한다, device/sim).
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace guard {

constexpr int SR = 16000;
constexpr int WINDOW = 16000;   // 1초
constexpr int NFFT = 1024;
constexpr int HOP = 512;
constexpr int N_FRAMES = (WINDOW - NFFT) / HOP + 1;  // 30
constexpr int N_MELS = 32;
constexpr int N_LOW = 3;
constexpr int N_FEATURES = 2 * N_MELS + N_LOW;      // 67
constexpr int K = 8;
constexpr int ITERATIONS = 30;
constexpr float OFF_RMS = 0.01f;
constexpr float SD_FLOOR = 1e-3f;
constexpr float CALIBRATION_MARGIN = 1.1f;
constexpr int START_AFTER = 3;
constexpr int END_AFTER = 5;
constexpr int SUMMARY_EVERY = 10;

// 특징 계산 ---------------------------------------------------------------
void init();                                            // 창·멜 필터 준비 (한 번)
float rms(const float* x);                              // x: WINDOW개
void features(const float* x, float* out);              // out: N_FEATURES개

// 모델 -----------------------------------------------------------------------
struct Model {
  float mean[N_FEATURES];
  float std[N_FEATURES];
  float centroids[K][N_FEATURES];
  float threshold;
  char id[24];
};
void load_factory(Model& m);                            // model_data.h의 기본 모델
float distance(const Model& m, const float* feats);
float score(const Model& m, const float* feats);        // 1 이상이면 이상
// 현장 보정: n개의 정상 특징(행 우선 [n][N_FEATURES])으로 다시 학습. work: n개의 float 작업 공간
void calibrate(Model& m, const float* feats, int n, float* work);

// 판단 규칙 ------------------------------------------------------------------
enum class State { Off, Running, Anomaly };
struct Message {
  enum Kind { None, AnomalyStart, AnomalyEnd, Reading } kind = None;
  float score = 0;          // 이벤트: 그때 점수
  int duration_s = 0;       // 이상 끝
  State state = State::Off; // 요약
  float score_avg = 0, score_max = 0;
  int anomaly_windows = 0;
};
class Detector {
 public:
  // 1초 결과 하나 → 보낼 메시지 (최대 2개: 이벤트 하나 + 요약 하나). 반환값 = 개수
  int update(float level, float score, Message out[2]);
  State state() const { return anomaly_ ? State::Anomaly : (last_running_ ? State::Running : State::Off); }

 private:
  bool anomaly_ = false, last_running_ = false;
  int over_ = 0, under_ = 0, tick_ = 0, started_at_ = 0;
  int n_ = 0, anomaly_windows_ = 0;
  float sum_ = 0, max_ = 0;
  bool saw_anomaly_ = false, saw_running_ = false;
};
const char* state_name(State s);

}  // namespace guard
