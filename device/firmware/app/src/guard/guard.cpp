// 판정 코드 구현. 수식은 model/features.py, model/kmeans.py, model/detector.py와 같다.
// 값이 같은지는 tests/device/test_core_matches_python.py가 PC 빌드(device/sim)로 확인한다.
#include "guard.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "model_data.h"

namespace guard {

namespace {

constexpr double PI = 3.14159265358979323846;
constexpr double FMIN = 20.0, FMAX = 7600.0;
constexpr double EPS_MEL = 1e-6, EPS_LOW = 1e-9;
constexpr int LOW_BANDS[N_LOW][2] = {{20, 32}, {45, 55}, {100, 150}};  // Hz = DFT 칸 (1초 창)

float frame_window[NFFT];
float twiddle_re[NFFT / 2], twiddle_im[NFFT / 2];
double mel_points[N_MELS + 2];  // Hz
float* dft_cos = nullptr;       // cos(2πj/WINDOW), WINDOW개 ┐ 큰 버퍼는 시작할 때 malloc으로 잡는다
float* xw = nullptr;            // 창을 곱한 1초 소리      ┘ (ESP32에서는 PSRAM에 잡혀 SRAM을 아낀다)
bool ready = false;

double hz_to_mel(double f) { return 2595.0 * log10(1.0 + f / 700.0); }
double mel_to_hz(double m) { return 700.0 * (pow(10.0, m / 2595.0) - 1.0); }

// 1024점 FFT (제자리, 기수 2)
void fft(float* re, float* im) {
  for (int i = 1, j = 0; i < NFFT; i++) {
    int bit = NFFT >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (int len = 2; len <= NFFT; len <<= 1) {
    int step = NFFT / len;
    for (int i = 0; i < NFFT; i += len) {
      for (int k = 0; k < len / 2; k++) {
        float wr = twiddle_re[k * step], wi = twiddle_im[k * step];
        int a = i + k, b = i + k + len / 2;
        float xr = re[b] * wr - im[b] * wi, xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr; im[b] = im[a] - xi;
        re[a] += xr; im[a] += xi;
      }
    }
  }
}

// 멜 필터 i가 FFT 칸 k에 주는 무게 (삼각형, 높이 1)
inline float mel_weight(int i, int k) {
  double f = (double)k * SR / NFFT;
  double lo = mel_points[i], c = mel_points[i + 1], hi = mel_points[i + 2];
  double w = fmin((f - lo) / (c - lo), (hi - f) / (hi - c));
  return w > 0 ? (float)w : 0.0f;
}

float sq_dist_z(const Model& m, const float* f, const float* c) {
  float d = 0;
  for (int j = 0; j < N_FEATURES; j++) {
    float z = (f[j] - m.mean[j]) / m.std[j] - c[j];
    d += z * z;
  }
  return d;
}

}  // namespace

void init() {
  if (ready) return;
  for (int i = 0; i < NFFT; i++) frame_window[i] = (float)(0.5 - 0.5 * cos(2 * PI * i / (NFFT - 1)));
  for (int k = 0; k < NFFT / 2; k++) {
    twiddle_re[k] = (float)cos(-2 * PI * k / NFFT);
    twiddle_im[k] = (float)sin(-2 * PI * k / NFFT);
  }
  double lo = hz_to_mel(FMIN), hi = hz_to_mel(FMAX);
  for (int i = 0; i < N_MELS + 2; i++) mel_points[i] = mel_to_hz(lo + (hi - lo) * i / (N_MELS + 1));
  dft_cos = (float*)malloc(sizeof(float) * WINDOW);
  xw = (float*)malloc(sizeof(float) * WINDOW);
  for (int j = 0; j < WINDOW; j++) dft_cos[j] = (float)cos(2 * PI * j / WINDOW);
  ready = true;
}

float rms(const float* x) {
  double s = 0;
  for (int i = 0; i < WINDOW; i++) s += (double)x[i] * x[i];
  return (float)sqrt(s / WINDOW);
}

void features(const float* x, float* out) {
  init();
  static float re[NFFT], im[NFFT];
  static float logmel[N_FRAMES][N_MELS];
  for (int f = 0; f < N_FRAMES; f++) {
    const float* frame = x + f * HOP;
    for (int i = 0; i < NFFT; i++) { re[i] = frame[i] * frame_window[i]; im[i] = 0; }
    fft(re, im);
    for (int i = 0; i < N_MELS; i++) {
      // 필터가 0이 아닌 칸만 더한다
      int k0 = (int)floor(mel_points[i] * NFFT / SR), k1 = (int)ceil(mel_points[i + 2] * NFFT / SR);
      if (k0 < 0) k0 = 0;
      if (k1 > NFFT / 2) k1 = NFFT / 2;
      double e = 0;
      for (int k = k0; k <= k1; k++) {
        float w = mel_weight(i, k);
        if (w > 0) e += (double)w * ((double)re[k] * re[k] + (double)im[k] * im[k]);
      }
      logmel[f][i] = (float)log(e + EPS_MEL);
    }
  }
  for (int i = 0; i < N_MELS; i++) {
    double s = 0, s2 = 0;
    for (int f = 0; f < N_FRAMES; f++) s += logmel[f][i];
    double mean = s / N_FRAMES;
    for (int f = 0; f < N_FRAMES; f++) { double d = logmel[f][i] - mean; s2 += d * d; }
    out[i] = (float)mean;
    out[N_MELS + i] = (float)sqrt(s2 / N_FRAMES);
  }
  // 1초 전체 Hann 창에서 저음 대역 비율. 필요한 칸만 직접 DFT로 구한다 (큰 FFT 없이)
  double total = 0;
  for (int n = 0; n < WINDOW; n++) {
    xw[n] = x[n] * (float)(0.5 - 0.5 * cos(2 * PI * n / (WINDOW - 1)));
    total += (double)xw[n] * xw[n];
  }
  total *= WINDOW;  // 파스발: 양쪽 스펙트럼 전체 에너지
  for (int b = 0; b < N_LOW; b++) {
    double band = 0;
    for (int k = LOW_BANDS[b][0]; k < LOW_BANDS[b][1]; k++) {
      float sr = 0, si = 0;
      long idx = 0;
      for (int n = 0; n < WINDOW; n++) {
        sr += xw[n] * dft_cos[idx];
        si -= xw[n] * dft_cos[(idx + WINDOW - WINDOW / 4) % WINDOW];  // sin(θ) = cos(θ - π/2)
        idx += k;
        if (idx >= WINDOW) idx -= WINDOW;
      }
      band += (double)sr * sr + (double)si * si;
    }
    out[2 * N_MELS + b] = (float)log(band / (total + 1e-12) + EPS_LOW);
  }
}

void load_factory(Model& m) {
  memcpy(m.mean, GUARD_MEAN, sizeof(m.mean));
  memcpy(m.std, GUARD_STD, sizeof(m.std));
  memcpy(m.centroids, GUARD_CENTROIDS, sizeof(m.centroids));
  m.threshold = GUARD_THRESHOLD;
  snprintf(m.id, sizeof(m.id), "%s", GUARD_MODEL_ID);
}

float distance(const Model& m, const float* feats) {
  float best = INFINITY;
  for (int c = 0; c < K; c++) {
    float d = sq_dist_z(m, feats, m.centroids[c]);
    if (d < best) best = d;
  }
  return sqrtf(best);
}

float score(const Model& m, const float* feats) { return distance(m, feats) / m.threshold; }

void calibrate(Model& m, const float* feats, int n, float* nearest) {
  // 표준화 (모집단 표준편차, 너무 작은 값은 SD_FLOOR로)
  for (int j = 0; j < N_FEATURES; j++) {
    double s = 0, s2 = 0;
    for (int i = 0; i < n; i++) s += feats[i * N_FEATURES + j];
    double mean = s / n;
    for (int i = 0; i < n; i++) { double d = feats[i * N_FEATURES + j] - mean; s2 += d * d; }
    m.mean[j] = (float)mean;
    double sd = sqrt(s2 / n);
    m.std[j] = (float)(sd > SD_FLOOR ? sd : SD_FLOOR);
  }
  // 첫 중심 = 표준화한 점들의 평균에 가장 가까운 점
  float zmean[N_FEATURES];
  for (int j = 0; j < N_FEATURES; j++) {
    double s = 0;
    for (int i = 0; i < n; i++) s += (feats[i * N_FEATURES + j] - m.mean[j]) / m.std[j];
    zmean[j] = (float)(s / n);
  }
  auto z = [&](int i, int j) { return (feats[i * N_FEATURES + j] - m.mean[j]) / m.std[j]; };
  auto sq_to = [&](int i, const float* c) {
    float d = 0;
    for (int j = 0; j < N_FEATURES; j++) { float t = z(i, j) - c[j]; d += t * t; }
    return d;
  };
  int first = 0;
  float best = INFINITY;
  for (int i = 0; i < n; i++) {
    float d = sq_to(i, zmean);
    if (d < best) { best = d; first = i; }
  }
  for (int j = 0; j < N_FEATURES; j++) m.centroids[0][j] = z(first, j);
  // 다음 중심 = 지금 중심들에서 가장 먼 점
  for (int i = 0; i < n; i++) nearest[i] = sq_to(i, m.centroids[0]);
  for (int c = 1; c < K; c++) {
    int far = 0;
    for (int i = 1; i < n; i++)
      if (nearest[i] > nearest[far]) far = i;
    for (int j = 0; j < N_FEATURES; j++) m.centroids[c][j] = z(far, j);
    for (int i = 0; i < n; i++) {
      float d = sq_to(i, m.centroids[c]);
      if (d < nearest[i]) nearest[i] = d;
    }
  }
  // Lloyd 반복. 빈 군집은 이전 중심을 그대로 둔다
  static double sums[K][N_FEATURES];
  int counts[K];
  for (int it = 0; it < ITERATIONS; it++) {
    memset(sums, 0, sizeof(sums));
    memset(counts, 0, sizeof(counts));
    for (int i = 0; i < n; i++) {
      int label = 0;
      float bd = INFINITY;
      for (int c = 0; c < K; c++) {
        float d = sq_to(i, m.centroids[c]);
        if (d < bd) { bd = d; label = c; }
      }
      counts[label]++;
      for (int j = 0; j < N_FEATURES; j++) sums[label][j] += z(i, j);
    }
    for (int c = 0; c < K; c++)
      if (counts[c])
        for (int j = 0; j < N_FEATURES; j++) m.centroids[c][j] = (float)(sums[c][j] / counts[c]);
  }
  // 기준 = 보정 데이터 거리의 최대값 × 여유
  m.threshold = 1.0f;
  float worst = 0;
  for (int i = 0; i < n; i++) {
    float d = distance(m, feats + i * N_FEATURES);
    if (d > worst) worst = d;
  }
  m.threshold = worst * CALIBRATION_MARGIN;
  snprintf(m.id, sizeof(m.id), "calibrated-%d", n);
}

int Detector::update(float level, float sc, Message out[2]) {
  int count = 0;
  tick_++;
  bool running = level >= OFF_RMS;
  last_running_ = running;
  if (!running) sc = 0;
  bool high = running && sc >= 1.0f;
  if (high) { over_++; under_ = 0; } else { under_++; over_ = 0; }
  if (!anomaly_ && over_ >= START_AFTER) {
    anomaly_ = true;
    started_at_ = tick_;
    out[count] = Message();
    out[count].kind = Message::AnomalyStart;
    out[count++].score = sc;
  } else if (anomaly_ && under_ >= END_AFTER) {
    anomaly_ = false;
    out[count] = Message();
    out[count].kind = Message::AnomalyEnd;
    out[count].score = sc;
    out[count++].duration_s = tick_ - started_at_;
  }
  saw_anomaly_ |= anomaly_;
  saw_running_ |= running;
  sum_ += sc;
  if (n_ == 0 || sc > max_) max_ = sc;
  if (high) anomaly_windows_++;
  if (++n_ == SUMMARY_EVERY) {
    out[count] = Message();
    out[count].kind = Message::Reading;
    out[count].state = saw_anomaly_ ? State::Anomaly : (saw_running_ ? State::Running : State::Off);
    out[count].score_avg = sum_ / n_;
    out[count].score_max = max_;
    out[count++].anomaly_windows = anomaly_windows_;
    n_ = 0; sum_ = 0; max_ = 0; anomaly_windows_ = 0;
    saw_anomaly_ = saw_running_ = false;
  }
  return count;
}

const char* state_name(State s) {
  switch (s) {
    case State::Anomaly: return "anomaly";
    case State::Running: return "running";
    default: return "off";
  }
}

}  // namespace guard
