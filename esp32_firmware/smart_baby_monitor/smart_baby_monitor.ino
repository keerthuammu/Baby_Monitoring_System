/*
 * ==============================================================================
 * Smart Baby Monitoring System — Production IoT Firmware
 * ==============================================================================
 * Description:
 *   Continuous acoustic feature extraction (RMS, Peak, Sound Level dB) via
 *   INMP441 I2S MEMS microphone, with real-time neural YAMNet baby crying
 *   classification on FastAPI Render backend.
 *
 * Hardware:
 *   - ESP32 DevKit V1
 *   - INMP441 I2S Digital MEMS Microphone
 *
 * Confirmed Pin Mapping:
 *   - SCK (Serial Clock)  -> GPIO 26
 *   - WS  (Word Select)   -> GPIO 25
 *   - SD  (Serial Data)   -> GPIO 33
 *   - VDD                 -> ESP32 3V3 (WARNING: Never connect to 5V!)
 *   - GND                 -> ESP32 GND
 *   - L/R                 -> ESP32 GND (Selects Left Channel)
 *
 * Arduino IDE Settings:
 *   - Board: "ESP32 Dev Module" (ESP32 by Espressif Systems v3.3.12)
 *   - Upload Speed: 921600 or 115200
 *   - Serial Monitor: 115200 baud
 * ==============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <driver/i2s.h>
#include <math.h>

// ==========================================
// 1. NETWORK & BACKEND CONFIGURATION
// ==========================================
// Enter your 2.4 GHz Wi-Fi credentials:
const char* WIFI_SSID     = "Nothing Phone 3a";
const char* WIFI_PASSWORD = "Keerthuammu29@";

// Target Ingestion Endpoint (Render Cloud Backend):
const char* BACKEND_URL        = "https://baby-monitor-backend-8m8o.onrender.com/api/readings";

// Audio Classification Endpoint (Render Cloud YAMNet ONNX Classification Service):
const char* AUDIO_CLASSIFY_URL = "https://baby-monitor-backend-8m8o.onrender.com/api/audio/classify";

// Security API Key (must match API_KEY in backend/.env):
const char* API_KEY            = "baby_monitor_device_secret_key_123";

// Unique Device Identifier:
const char* DEVICE_ID          = "esp32-nursery-01";

// Transmission interval in milliseconds (3000 ms gives responsive telemetry):
const unsigned long TRANSMIT_INTERVAL_MS = 3000;

// Audio classification chunk interval (at most once every 3500 ms during high sound/cry):
const unsigned long AUDIO_CHUNK_INTERVAL_MS = 3500;

// ==========================================
// 2. I2S MICROPHONE CONFIGURATION
// ==========================================
#define I2S_SCK_PIN       26
#define I2S_WS_PIN        25
#define I2S_SD_PIN        33

#define I2S_PORT          I2S_NUM_0
#define SAMPLE_RATE       16000
#define CHUNK_SIZE        512

// 1.0 second continuous circular buffer of 16-bit 16kHz PCM audio (32 KB RAM)
#define AUDIO_BUFFER_SAMPLES 16000

// ==========================================
// GLOBAL STATE VARIABLES
// ==========================================
unsigned long lastTransmitTime = 0;
unsigned long lastAudioTransmitTime = 0;
unsigned long lastWifiRetryTime = 0;
unsigned long rateLimitCooldownUntil = 0;
unsigned long lastCryDetectedTime = 0;  // Infant crying episode hold timer
bool wifiConnected = false;

// Audio window accumulation for sound intensity (dB & RMS)
double windowSumSquares = 0.0;
int32_t windowPeak = 0;
unsigned long windowSamplesCount = 0;
double currentSoundLevelDb = 0.0;

// Continuous circular PCM audio buffer
int16_t audioBuffer[AUDIO_BUFFER_SAMPLES];
int audioBufferHead = 0;
int audioTotalBuffered = 0;

// Initialize the ESP32 I2S Driver for INMP441
void setupI2S() {
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = CHUNK_SIZE,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK_PIN,
    .ws_io_num = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD_PIN
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Failed to install I2S driver: %d\n", err);
    while (true) delay(1000);
  }

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Failed to assign I2S pins: %d\n", err);
    while (true) delay(1000);
  }

  Serial.println("[OK] INMP441 I2S Microphone configured successfully.");
}

// Connect to Wi-Fi robustly
void checkWifiConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConnected) {
      wifiConnected = true;
      Serial.println("\n----------------------------------------");
      Serial.printf("[WIFI] Connected! Assigned IP: %s\n", WiFi.localIP().toString().c_str());
      Serial.printf("[WIFI] Target Backend: %s\n", BACKEND_URL);
      Serial.println("----------------------------------------");
    }
    return;
  }

  wifiConnected = false;
  unsigned long now = millis();
  if (now - lastWifiRetryTime > 15000) {
    lastWifiRetryTime = now;
    Serial.printf("[WIFI] Connecting to SSID: '%s'...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// Focused Infant Distress Pitch Analyzer (320 Hz - 720 Hz)
// Searches infant cry fundamental frequencies using autocorrelation over recent 1024 samples
float detectInfantCryPitch(float sampleRate, float* outPeriodicity) {
  if (audioTotalBuffered < 1024) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f;
  }

  // Linearize last 1024 samples from circular buffer
  int16_t slice[1024];
  int start = (audioBufferHead - 1024 + AUDIO_BUFFER_SAMPLES) % AUDIO_BUFFER_SAMPLES;
  for (int i = 0; i < 1024; i++) {
    slice[i] = audioBuffer[(start + i) % AUDIO_BUFFER_SAMPLES];
  }

  int testLen = 512;
  int minLag = 22; // ~727 Hz
  int maxLag = 50; // ~320 Hz

  int64_t energy0 = 0;
  for (int i = 0; i < testLen; i++) {
    energy0 += (int32_t)slice[i] * (int32_t)slice[i];
  }

  if (energy0 < 10000) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f;
  }

  int64_t maxCorr = 0;
  int bestLag = 0;

  for (int lag = minLag; lag <= maxLag; lag++) {
    int64_t corr = 0;
    for (int i = 0; i < testLen; i++) {
      corr += (int32_t)slice[i] * (int32_t)slice[i + lag];
    }
    if (corr > maxCorr) {
      maxCorr = corr;
      bestLag = lag;
    }
  }

  float periodicity = (float)maxCorr / (float)energy0;
  if (outPeriodicity) *outPeriodicity = periodicity;

  // Real infant cries through phone speakers or across room have periodicity ~0.40 - 0.85
  if (periodicity >= 0.40f && bestLag > 0) {
    return sampleRate / (float)bestLag;
  }
  return 0.0f;
}

// Transmit calculated features to FastAPI backend
void sendTelemetryToBackend(float soundLevel, float rms, int peak, const char* classification, float pitchHz, float confidence) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Skipped: Wi-Fi offline. Continuing local sound monitoring.");
    return;
  }

  if (millis() < rateLimitCooldownUntil) {
    unsigned long remainingSec = (rateLimitCooldownUntil - millis()) / 1000 + 1;
    Serial.printf("[RATE LIMIT 429] In cooldown (%lu s remaining). Telemetry skipped.\n", remainingSec);
    return;
  }

  HTTPClient http;
  String urlStr = String(BACKEND_URL);

  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (urlStr.startsWith("https://")) {
    secureClient.setInsecure();
    secureClient.setTimeout(6000);
    http.begin(secureClient, BACKEND_URL);
  } else {
    plainClient.setTimeout(3000);
    http.begin(plainClient, BACKEND_URL);
  }
  http.setTimeout(6000);

  http.addHeader("Content-Type", "application/json");
  http.addHeader("Accept", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("User-Agent", "SmartBabyMonitor-ESP32/2.1");

  char jsonBuffer[384];
  snprintf(
    jsonBuffer,
    sizeof(jsonBuffer),
    "{\"device_id\":\"%s\",\"sound_level\":%.2f,\"rms_amplitude\":%.2f,\"peak_amplitude\":%d,\"classification\":\"%s\",\"pitch_hz\":%.1f,\"confidence\":%.2f,\"source\":\"esp32_device\"}",
    DEVICE_ID,
    soundLevel,
    rms,
    peak,
    classification,
    pitchHz,
    confidence
  );

  int httpCode = http.POST(String(jsonBuffer));

  if (httpCode == HTTP_CODE_CREATED || httpCode == HTTP_CODE_OK) {
    Serial.printf("[HTTP 201] Sent -> %.1f dB | %s (%.0f%%) | Pitch: %.0f Hz | RMS: %.1f\n", soundLevel, classification, confidence * 100.0f, pitchHz, rms);
  } else if (httpCode == 429) {
    Serial.println("[RATE LIMIT 429] Cloud rate limit triggered. Pausing HTTPS for 10s...");
    rateLimitCooldownUntil = millis() + 10000;
  } else if (httpCode == 502 || httpCode == 503 || httpCode == 504) {
    Serial.printf("[HTTP %d] Backend restarting or waking up. Retrying in 8s...\n", httpCode);
    rateLimitCooldownUntil = millis() + 8000;
  } else if (httpCode > 0) {
    String resp = http.getString();
    Serial.printf("[HTTP ERROR %d] %s\n", httpCode, resp.substring(0, 80).c_str());
  } else {
    Serial.printf("[HTTP FAILED] Backend unreachable (%s)\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

// Transmit the most recent 1.0 second of raw 16kHz PCM audio to YAMNet classifier
void sendAudioChunkToBackend() {
  if (WiFi.status() != WL_CONNECTED || audioTotalBuffered < 8000) return;

  if (millis() < rateLimitCooldownUntil) {
    return;
  }

  HTTPClient http;
  String audioUrl = String(AUDIO_CLASSIFY_URL);

  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (audioUrl.startsWith("https://")) {
    secureClient.setInsecure();
    secureClient.setTimeout(6000);
    http.begin(secureClient, audioUrl);
  } else {
    plainClient.setTimeout(3000);
    http.begin(plainClient, audioUrl);
  }
  http.setTimeout(6000);

  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("Accept", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("User-Agent", "SmartBabyMonitor-ESP32/2.1");

  // Unroll circular buffer into linear 16000 samples (32KB)
  int samplesToSend = (audioTotalBuffered >= AUDIO_BUFFER_SAMPLES) ? AUDIO_BUFFER_SAMPLES : audioTotalBuffered;
  static int16_t linearBuf[AUDIO_BUFFER_SAMPLES];
  int start = (audioBufferHead - samplesToSend + AUDIO_BUFFER_SAMPLES) % AUDIO_BUFFER_SAMPLES;
  for (int i = 0; i < samplesToSend; i++) {
    linearBuf[i] = audioBuffer[(start + i) % AUDIO_BUFFER_SAMPLES];
  }

  int httpCode = http.POST((uint8_t*)linearBuf, samplesToSend * sizeof(int16_t));
  if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
    String resp = http.getString();
    Serial.printf("[YAMNet AUDIO] 16kHz chunk sent -> HTTP %d | %s\n", httpCode, resp.substring(0, 100).c_str());
    if (resp.indexOf("BABY CRYING DETECTED") >= 0 || resp.indexOf("BABY_CRYING_DETECTED") >= 0) {
      lastCryDetectedTime = millis();
      Serial.println(">>> 🚨 YAMNET NEURAL NETWORK CONFIRMED BABY CRYING! 🚨 <<<");
    }
  } else if (httpCode == 429) {
    Serial.println("[RATE LIMIT 429] Audio stream rate limited. Pausing HTTPS for 10s...");
    rateLimitCooldownUntil = millis() + 10000;
  } else if (httpCode == 502 || httpCode == 503 || httpCode == 504) {
    Serial.printf("[YAMNet AUDIO] Backend unavailable (%d). Retrying in 8s...\n", httpCode);
    rateLimitCooldownUntil = millis() + 8000;
  } else if (httpCode > 0) {
    Serial.printf("[YAMNet AUDIO ERROR] Server responded: %d\n", httpCode);
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println("\n=======================================================");
  Serial.println("   Smart Baby Monitoring System — ESP32 IoT Node   ");
  Serial.println("=======================================================");
  Serial.printf("Device ID: %s\n", DEVICE_ID);
  Serial.printf("Telemetry Interval: %lu ms | Audio Interval: %lu ms\n", TRANSMIT_INTERVAL_MS, AUDIO_CHUNK_INTERVAL_MS);

  // 1. Setup I2S Audio Hardware
  setupI2S();

  // 2. Begin Wi-Fi Connection
  Serial.printf("[WIFI] Connecting to '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void loop() {
  // 1. Check Wi-Fi state non-blockingly
  checkWifiConnection();

  // 2. Read audio samples from INMP441 DMA buffer
  int32_t raw_samples[CHUNK_SIZE];
  size_t bytes_read = 0;

  esp_err_t result = i2s_read(I2S_PORT, &raw_samples, sizeof(raw_samples), &bytes_read, 50 / portTICK_PERIOD_MS);

  if (result == ESP_OK && bytes_read > 0) {
    int samples_read = bytes_read / sizeof(int32_t);

    for (int i = 0; i < samples_read; i++) {
      // INMP441: 24-bit audio MSB-aligned in 32-bit slot.
      // Shifting >> 13 provides calibrated acoustic gain:
      // Normal speech ~55-65 dB, close clap/cry ~70-80 dB
      int32_t sample_raw = raw_samples[i] >> 13;

      // 1st-order IIR DC-removal high-pass filter (cutoff ~20 Hz at 16kHz)
      static float prev_x = 0.0f;
      static float prev_y = 0.0f;
      float x = (float)sample_raw;
      float y = x - prev_x + 0.995f * prev_y;
      prev_x = x;
      prev_y = y;
      int32_t sample = (int32_t)constrain(y, -32768.0f, 32767.0f);
      int32_t abs_sample = abs(sample);

      if (abs_sample > windowPeak) {
        windowPeak = abs_sample;
      }
      windowSumSquares += (double)sample * (double)sample;

      // Continuous circular accumulation of recent audio samples
      audioBuffer[audioBufferHead] = (int16_t)sample;
      audioBufferHead = (audioBufferHead + 1) % AUDIO_BUFFER_SAMPLES;
      if (audioTotalBuffered < AUDIO_BUFFER_SAMPLES) {
        audioTotalBuffered++;
      }
    }
    windowSamplesCount += samples_read;
  }

  unsigned long now = millis();

  // 3. Audio Chunk Transmission to YAMNet Neural Inference
  // Triggers whenever sound is elevated (>= 58 dB) or during active crying hold, staggered from telemetry
  if (now - lastAudioTransmitTime >= AUDIO_CHUNK_INTERVAL_MS) {
    bool isSoundElevated = (currentSoundLevelDb >= 58.0f);
    bool isRecentCry = (now - lastCryDetectedTime < 5000);
    if ((isSoundElevated || isRecentCry) && (now - lastTransmitTime >= 800)) {
      lastAudioTransmitTime = now;
      sendAudioChunkToBackend();
    }
  }

  // 4. Periodic Sound Intensity Telemetry & Classification (every 3000 ms)
  if (now - lastTransmitTime >= TRANSMIT_INTERVAL_MS) {
    lastTransmitTime = now;

    if (windowSamplesCount > 0) {
      double rms = sqrt(windowSumSquares / windowSamplesCount);
      double soundLevel = 20.0 * log10(rms > 1.0 ? rms : 1.0);
      currentSoundLevelDb = soundLevel;

      // Edge Pitch Analysis (320 Hz - 720 Hz infant distress band)
      float periodicity = 0.0f;
      float pitch = 0.0f;
      if (soundLevel >= 48.0 && audioTotalBuffered >= 1024) {
        pitch = detectInfantCryPitch(SAMPLE_RATE, &periodicity);
      }

      // Feature A: Sound Intensity (Volume level)
      const char* intensity = "LOW SOUND";
      if (soundLevel >= 65.0f) {
        intensity = "HIGH SOUND";
      } else if (soundLevel >= 45.0f) {
        intensity = "MODERATE SOUND";
      }

      // Feature B: Baby Sound Status & Edge Acoustic Telemetry
      const char* babyStatus = "NOT BABY CRYING";
      const char* classification = "QUIET";
      float confidence = 0.85f;

      bool isCryPitch = (pitch >= 320.0f && pitch <= 720.0f) && (periodicity >= 0.40f);
      static int consecutiveVoicedFrames = 0;

      if (isCryPitch && soundLevel >= 50.0f) {
        consecutiveVoicedFrames++;
        if (consecutiveVoicedFrames >= 2) {
          lastCryDetectedTime = now;
          Serial.printf("[ACOUSTIC PITCH] Infant crying frequency: %.1f Hz (periodicity: %.2f)\n", pitch, periodicity);
        }
      } else {
        consecutiveVoicedFrames = 0;
      }

      // Active cry episode: maintained by YAMNet confirmation or consecutive edge pitch
      bool isCryEpisodeActive = (now - lastCryDetectedTime < 5000) && (soundLevel >= 45.0f);

      if (isCryEpisodeActive) {
        babyStatus = "🚨 BABY CRYING DETECTED";
        classification = "BABY_CRYING_DETECTED";
        confidence = 0.92f;
      } else if (isCryPitch) {
        babyStatus = "⚠️ POSSIBLE BABY CRY";
        classification = "POSSIBLE_CRYING";
        confidence = 0.85f;
      } else if (soundLevel >= 65.0f) {
        classification = "HIGH_SOUND";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.88f;
      } else if (soundLevel >= 45.0f) {
        classification = "MODERATE_SOUND";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.85f;
      } else {
        classification = "QUIET";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.95f;
      }

      Serial.printf("[SOUND] Level: %5.1f dB | Intensity: [%s] | Status: [%s] | Pitch: %.0f Hz\n",
                    soundLevel, intensity, babyStatus, pitch);

      sendTelemetryToBackend(soundLevel, rms, windowPeak, classification, pitch, confidence);

      // Reset window accumulators
      windowSumSquares = 0.0;
      windowPeak = 0;
      windowSamplesCount = 0;
    }
  }
}
