 /*
 * ==============================================================================
 * Smart Baby Monitoring System — Production IoT Firmware
 * ==============================================================================
 * Description:
 *   Continuous acoustic feature extraction (RMS, Peak, Sound Level dB) via
 *   INMP441 I2S MEMS microphone, transmitted to local FastAPI backend over Wi-Fi.
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

// Transmission interval in milliseconds (3000 ms avoids Cloudflare free-tier rate limits):
const unsigned long TRANSMIT_INTERVAL_MS = 3000;

// Audio classification chunk interval (6000 ms for neural inference during elevated sound):
const unsigned long AUDIO_CHUNK_INTERVAL_MS = 6000;

// ==========================================
// 2. I2S MICROPHONE CONFIGURATION
// ==========================================
#define I2S_SCK_PIN       26
#define I2S_WS_PIN        25
#define I2S_SD_PIN        33

#define I2S_PORT          I2S_NUM_0
#define SAMPLE_RATE       16000
#define CHUNK_SIZE        512

// 1.0 second of 16-bit 16kHz PCM audio buffer (32 KB RAM)
#define AUDIO_BUFFER_SAMPLES 16000

// ==========================================
// GLOBAL STATE VARIABLES
// ==========================================
unsigned long lastTransmitTime = 0;
unsigned long lastAudioTransmitTime = 0;
unsigned long lastWifiRetryTime = 0;
unsigned long rateLimitCooldownUntil = 0;
unsigned long lastCryDetectedTime = 0;  // Infant crying episode hold timer (8 seconds)
bool wifiConnected = false;

// Audio window accumulation for sound intensity (dB & RMS)
double windowSumSquares = 0.0;
int32_t windowPeak = 0;
unsigned long windowSamplesCount = 0;
double currentSoundLevelDb = 0.0;

// Raw PCM audio buffer for local YAMNet baby crying classification
int16_t audioBuffer[AUDIO_BUFFER_SAMPLES];
int audioBufferIdx = 0;


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
  // Retry periodically if connection dropped, without aborting active handshake
  if (now - lastWifiRetryTime > 20000) {
    lastWifiRetryTime = now;
    Serial.printf("[WIFI] Attempting connection to SSID: '%s'...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// Full-Spectrum Human Pitch Autocorrelation Analyzer
// Searches complete vocal frequency range (85 Hz to 800 Hz) to cleanly distinguish
// infant crying (330 Hz - 680 Hz) from adult voice (85 Hz - 250 Hz) and noise.
float detectInfantCryPitch(const int16_t* buffer, int len, float sampleRate, float* outPeriodicity) {
  if (len < 512) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f;
  }

  // Full human pitch lag search bounds:
  // 800 Hz -> lag = 20
  // 85 Hz  -> lag = 188
  int minLag = 20;   // 800 Hz
  int maxLag = 188;  // 85 Hz
  int testLen = 512; // ~32 ms slice for strong fundamental period tracking

  // If buffer has multiple slices, pick slice with highest signal energy
  int bestOffset = 0;
  int64_t maxSliceEnergy = 0;
  for (int offset = 0; offset + testLen + maxLag <= len; offset += 256) {
    int64_t sliceEnergy = 0;
    for (int i = 0; i < testLen; i++) {
      sliceEnergy += (int32_t)buffer[offset + i] * (int32_t)buffer[offset + i];
    }
    if (sliceEnergy > maxSliceEnergy) {
      maxSliceEnergy = sliceEnergy;
      bestOffset = offset;
    }
  }

  int64_t energy0 = maxSliceEnergy;
  if (energy0 < 10000) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f; // Silence / ambient
  }

  // Search for autocorrelation peaks across lag window
  int64_t corrValues[192];
  int64_t globalMaxCorr = 0;

  for (int lag = minLag; lag <= maxLag; lag++) {
    int64_t corr = 0;
    for (int i = 0; i < testLen; i++) {
      corr += (int32_t)buffer[bestOffset + i] * (int32_t)buffer[bestOffset + i + lag];
    }
    corrValues[lag] = corr;
    if (corr > globalMaxCorr) {
      globalMaxCorr = corr;
    }
  }

  float periodicity = (float)globalMaxCorr / (float)energy0;
  if (outPeriodicity) *outPeriodicity = periodicity;

  // Stricter normalized autocorrelation threshold (0.65) rejects room noise, hum, and broad speech
  if (periodicity < 0.65f || globalMaxCorr <= 0) {
    return 0.0f;
  }

  // First local maximum that reaches 70% of globalMaxCorr avoids harmonic octave halving
  int64_t threshold = (int64_t)(globalMaxCorr * 0.70f);
  int fundamentalLag = 0;

  for (int lag = minLag + 1; lag < maxLag; lag++) {
    if (corrValues[lag] > corrValues[lag - 1] && corrValues[lag] >= corrValues[lag + 1]) {
      if (corrValues[lag] >= threshold) {
        fundamentalLag = lag;
        break;
      }
    }
  }

  if (fundamentalLag > 0) {
    return sampleRate / (float)fundamentalLag;
  }
  return 0.0f;
}

// Transmit calculated features to FastAPI backend
void sendTelemetryToBackend(float soundLevel, float rms, int peak, const char* classification, float pitchHz, float confidence) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Skipped: Wi-Fi offline. Continuing local sound monitoring.");
    return;
  }

  // Active Rate-Limit Cooldown Protection (avoids Cloudflare DDoS trigger)
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
    secureClient.setInsecure(); // Permits SSL handshake with Render cloud
    secureClient.setTimeout(8000); // 8.0s for mobile hotspot SSL handshake
    http.begin(secureClient, BACKEND_URL);
  } else {
    plainClient.setTimeout(3000);
    http.begin(plainClient, BACKEND_URL);
  }
  http.setTimeout(8000);

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("User-Agent", "ESP32-SmartBabyMonitor/1.1");

  // Construct JSON payload with classification & pitch
  char jsonBuffer[384];
  snprintf(
    jsonBuffer,
    sizeof(jsonBuffer),
    "{\"device_id\":\"%s\",\"sound_level\":%.2f,\"rms_amplitude\":%.2f,\"peak_amplitude\":%d,\"classification\":\"%s\",\"pitch_hz\":%.1f,\"confidence\":%.2f}",
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
    Serial.println("[HTTP ERROR 429] Render/Cloudflare rate limit hit! Backing off for 10s to let rate limiter reset...");
    rateLimitCooldownUntil = millis() + 10000;
  } else if (httpCode == 502 || httpCode == 503 || httpCode == 504) {
    Serial.printf("[HTTP %d] Render backend is deploying or waking from cold start. Pausing 6s...\n", httpCode);
    rateLimitCooldownUntil = millis() + 6000;
  } else if (httpCode > 0) {
    String resp = http.getString();
    Serial.printf("[HTTP ERROR %d] %s\n", httpCode, resp.substring(0, 80).c_str());
  } else {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("[HTTP FAILED] Target backend refused or unreachable (%s) at %s\n", http.errorToString(httpCode).c_str(), BACKEND_URL);
    } else {
      Serial.println("[HTTP FAILED] Wi-Fi disconnected. Reconnecting to hotspot...");
    }
  }

  http.end();
}

// Transmit buffered 16kHz PCM audio chunk to local YAMNet classifier
void sendAudioChunkToBackend() {
  if (WiFi.status() != WL_CONNECTED || audioBufferIdx < 8000) return;

  if (millis() < rateLimitCooldownUntil) {
    audioBufferIdx = 0; // Drop buffer during cooldown
    return;
  }

  HTTPClient http;
  String audioUrl = String(AUDIO_CLASSIFY_URL);

  // Auto-adapt: If BACKEND_URL points to cloud via HTTPS, automatically route audio chunks to cloud classify endpoint
  if (String(BACKEND_URL).startsWith("https://") && String(BACKEND_URL).indexOf("/api/readings") >= 0) {
    audioUrl = String(BACKEND_URL);
    audioUrl.replace("/api/readings", "/api/audio/classify");
  }

  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (audioUrl.startsWith("https://")) {
    secureClient.setInsecure();
    secureClient.setTimeout(8000);
    http.begin(secureClient, audioUrl);
  } else {
    plainClient.setTimeout(3000);
    http.begin(plainClient, audioUrl);
  }
  http.setTimeout(8000);

  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("User-Agent", "ESP32-SmartBabyMonitor/1.1");

  int httpCode = http.POST((uint8_t*)audioBuffer, audioBufferIdx * sizeof(int16_t));
  if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
    Serial.printf("[YAMNet AUDIO] Transmitted %d samples (HTTP %d)\n", audioBufferIdx, httpCode);
  } else if (httpCode == 429) {
    Serial.println("[YAMNet AUDIO ERROR 429] Rate limit hit on audio stream. Backing off for 10s...");
    rateLimitCooldownUntil = millis() + 10000;
  } else if (httpCode == 502 || httpCode == 503 || httpCode == 504) {
    Serial.printf("[YAMNet AUDIO ERROR %d] Backend deploying/rebooting. Pausing 6s...\n", httpCode);
    rateLimitCooldownUntil = millis() + 6000;
  } else if (httpCode > 0) {
    Serial.printf("[YAMNet AUDIO ERROR] Server responded with code: %d\n", httpCode);
  }

  http.end();
  // Reset audio buffer index for next window
  audioBufferIdx = 0;
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

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 14) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("\n----------------------------------------");
    Serial.printf("[WIFI] Connected! Assigned IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[WIFI] Target Backend: %s\n", BACKEND_URL);
    Serial.println("----------------------------------------");
  } else {
    Serial.println("\n[WIFI] Initial handshake pending. Continuing in background...");
  }
  lastWifiRetryTime = millis();
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
      // INMP441 provides 24-bit audio MSB-aligned in 32-bit slot (bits 31..8)
      // Standard 16-bit extraction without digital distortion: Shift >> 16
      int32_t sample_raw = raw_samples[i] >> 16;

      // 1st-order IIR DC-removal high-pass filter (cutoff ~20 Hz at 16kHz)
      // y[n] = x[n] - x[n-1] + 0.995 * y[n-1]
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

      // Accumulate raw audio samples for local YAMNet classification
      if (audioBufferIdx < AUDIO_BUFFER_SAMPLES) {
        audioBuffer[audioBufferIdx++] = (int16_t)sample;
      }
    }
    windowSamplesCount += samples_read;
  }

  unsigned long now = millis();

  // 3. Periodic Sound Intensity Telemetry & Acoustic Classification (every 2000 ms)
  if (now - lastTransmitTime >= TRANSMIT_INTERVAL_MS) {
    lastTransmitTime = now;

    if (windowSamplesCount > 0) {
      double rms = sqrt(windowSumSquares / windowSamplesCount);
      // Normalized sound level score (approximate dB SPL mapping)
      double soundLevel = 20.0 * log10(rms > 1.0 ? rms : 1.0);
      currentSoundLevelDb = soundLevel;

      // Edge Pitch Analysis for Infant Cry Detection (350 Hz - 680 Hz)
      float periodicity = 0.0f;
      float pitch = 0.0f;
      if (soundLevel >= 50.0 && audioBufferIdx >= 512) {
        pitch = detectInfantCryPitch(audioBuffer, audioBufferIdx, SAMPLE_RATE, &periodicity);
      }

      // Feature A: Sound Intensity (Volume level)
      const char* intensity = "LOW SOUND";
      if (soundLevel >= 65.0f) {
        intensity = "HIGH SOUND";
      } else if (soundLevel >= 45.0f) {
        intensity = "MODERATE SOUND";
      }

      // Feature B: Baby Sound Status & Edge Acoustic Telemetry
      // Clearly decoupled: Volume Intensity (Feature A) vs Baby Sound Classification (Feature B)
      // YAMNet neural inference via /api/audio/classify is the sole authority for baby crying.
      // Pitch autocorrelation is sent as supporting telemetry only.
      const char* babyStatus = "NOT BABY CRYING";
      const char* classification = "QUIET";
      float confidence = 0.85f;

      // Stricter pitch voicing test: periodicity >= 0.65 in infant distress band (380 - 680 Hz)
      bool isCryPitch = (pitch >= 380.0f && pitch <= 680.0f) && (periodicity >= 0.65f);
      static int consecutiveVoicedFrames = 0;

      if (isCryPitch && soundLevel >= 52.0f) {
        consecutiveVoicedFrames++;
        if (consecutiveVoicedFrames >= 2) {
          lastCryDetectedTime = now;
          Serial.printf("[ACOUSTIC PITCH] Verified infant crying frequency: %.1f Hz (periodicity: %.2f)\n", pitch, periodicity);
        }
      } else {
        consecutiveVoicedFrames = 0;
      }

      // Short breath-pause latch (max 4.0s) strictly requires elevated sound
      bool isCryEpisodeActive = (now - lastCryDetectedTime < 4000) && (consecutiveVoicedFrames >= 2);

      if (isCryEpisodeActive) {
        babyStatus = "🚨 POSSIBLE BABY CRY";
        classification = "POSSIBLE_CRYING";
        confidence = 0.90f;
      } else if (soundLevel >= 65.0f) {
        // High non-crying sound (door slam, loud conversation, clapping, domestic noise)
        classification = "HIGH_SOUND";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.88f;
      } else if (soundLevel >= 45.0f) {
        // Moderate non-crying sound (routine conversation, footsteps, movement)
        classification = "MODERATE_SOUND";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.85f;
      } else {
        // Calm ambient room
        classification = "QUIET";
        babyStatus = "NOT BABY CRYING";
        confidence = 0.95f;
      }

      // Explicit Serial Monitor output: Clearly shows Volume, Baby Crying Status, and Pitch
      Serial.printf("[SOUND] Level: %5.1f dB | Intensity: [%s] | Status: [%s] | Pitch: %.0f Hz\n",
                    soundLevel, intensity, babyStatus, pitch);

      // Transmit telemetry to FastAPI backend
      sendTelemetryToBackend(soundLevel, rms, windowPeak, classification, pitch, confidence);

      // Reset window accumulators
      windowSumSquares = 0.0;
      windowPeak = 0;
      windowSamplesCount = 0;
    }
  }

  // 4. Stream Audio Chunk for YAMNet Neural Inference (only during elevated sound / crying episodes)
  // Staggered by at least 1500 ms after telemetry to avoid dual-burst HTTPS rate limits
  if (now - lastAudioTransmitTime >= AUDIO_CHUNK_INTERVAL_MS && (now - lastTransmitTime >= 1500)) {
    lastAudioTransmitTime = now;
    if (now - lastCryDetectedTime < 5000 || currentSoundLevelDb >= 50.0f) {
      sendAudioChunkToBackend();
    } else {
      audioBufferIdx = 0; // Clear ambient audio buffer to prevent backlog
    }
  }
}
