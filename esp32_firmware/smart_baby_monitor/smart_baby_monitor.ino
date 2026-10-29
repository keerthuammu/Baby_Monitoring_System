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

// Target Ingestion Endpoint (Appended with /api/readings):
// Can be set to local Windows IP e.g. "http://192.168.55.208:8000/api/readings" or Render cloud:
const char* BACKEND_URL        = "http://192.168.55.208:8000/api/readings";

// Local Audio Classification Endpoint (Windows machine running YAMNet locally):
const char* AUDIO_CLASSIFY_URL = "http://192.168.55.208:8000/api/audio/classify";

// Security API Key (must match API_KEY in backend/.env):
const char* API_KEY            = "baby_monitor_device_secret_key_123";

// Unique Device Identifier:
const char* DEVICE_ID          = "esp32-nursery-01";

// Transmission interval in milliseconds (2000 ms recommended):
const unsigned long TRANSMIT_INTERVAL_MS = 2000;

// Audio classification chunk interval (2500 ms recommended):
const unsigned long AUDIO_CHUNK_INTERVAL_MS = 2500;

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
bool wifiConnected = false;

// Audio window accumulation for sound intensity (dB & RMS)
double windowSumSquares = 0.0;
int32_t windowPeak = 0;
unsigned long windowSamplesCount = 0;

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

// Connect to Wi-Fi non-blockingly
void checkWifiConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConnected) {
      wifiConnected = true;
      Serial.println("\n----------------------------------------");
      Serial.print("[WIFI] Connected! Assigned IP: ");
      Serial.println(WiFi.localIP());
      Serial.print("[WIFI] Target Backend: ");
      Serial.println(BACKEND_URL);
      Serial.println("----------------------------------------");
    }
    return;
  }

  wifiConnected = false;
  unsigned long now = millis();
  if (now - lastWifiRetryTime > 10000) {
    lastWifiRetryTime = now;
    Serial.print("[WIFI] Connecting to SSID: ");
    Serial.println(WIFI_SSID);
    WiFi.disconnect();
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// Acoustic Pitch Autocorrelation Analyzer for Infant Cry Detection
// Infant cries produce a fundamental pitch F0 between 350 Hz and 680 Hz (optimal voicing peak ~450-500 Hz)
float detectInfantCryPitch(const int16_t* buffer, int len, float sampleRate, float* outPeriodicity) {
  if (len < 512) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f;
  }

  // Cry lag window at 16kHz:
  // 680 Hz -> lag = 16000 / 680 ≈ 23
  // 330 Hz -> lag = 16000 / 330 ≈ 48
  int minLag = 23;
  int maxLag = 48;
  int testLen = (len - maxLag > 400) ? 400 : (len - maxLag);

  int64_t energy0 = 0;
  for (int i = 0; i < testLen; i++) {
    energy0 += (int32_t)buffer[i] * (int32_t)buffer[i];
  }
  if (energy0 < 10000) {
    if (outPeriodicity) *outPeriodicity = 0.0f;
    return 0.0f;
  }

  int bestLag = 0;
  int64_t maxCorr = 0;

  for (int lag = minLag; lag <= maxLag; lag++) {
    int64_t corr = 0;
    for (int i = 0; i < testLen; i++) {
      corr += (int32_t)buffer[i] * (int32_t)buffer[i + lag];
    }
    if (corr > maxCorr) {
      maxCorr = corr;
      bestLag = lag;
    }
  }

  float periodicity = (float)maxCorr / (float)energy0;
  if (outPeriodicity) *outPeriodicity = periodicity;

  if (bestLag > 0 && periodicity >= 0.28f) {
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

  HTTPClient http;
  String urlStr = String(BACKEND_URL);

  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (urlStr.startsWith("https://")) {
    secureClient.setInsecure(); // Permits SSL handshake with Render cloud
    secureClient.setTimeout(6000);
    http.begin(secureClient, BACKEND_URL);
  } else {
    plainClient.setTimeout(4000);
    http.begin(plainClient, BACKEND_URL);
  }
  http.setTimeout(6000); // 6.0 second timeout for cloud HTTPS latency

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("User-Agent", "ESP32-BabyMonitor/1.0");

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
  } else if (httpCode > 0) {
    String resp = http.getString();
    Serial.printf("[HTTP ERROR %d] %s\n", httpCode, resp.c_str());
  } else {
    Serial.printf("[HTTP FAILED] Connection failed (%s). Check Wi-Fi connection.\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

// Transmit buffered 16kHz PCM audio chunk to local YAMNet classifier
void sendAudioChunkToBackend() {
  if (WiFi.status() != WL_CONNECTED || audioBufferIdx < 8000) return;

  HTTPClient http;
  String audioUrl = String(AUDIO_CLASSIFY_URL);

  // If AUDIO_CLASSIFY_URL was left on local IP while BACKEND_URL points to cloud, auto-adapt:
  if (String(BACKEND_URL).indexOf("/api/readings") >= 0 && audioUrl.indexOf("192.168") >= 0 && String(BACKEND_URL).startsWith("https://")) {
    audioUrl = String(BACKEND_URL);
    audioUrl.replace("/api/readings", "/api/audio/classify");
  }

  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (audioUrl.startsWith("https://")) {
    secureClient.setInsecure();
    secureClient.setTimeout(5000);
    http.begin(secureClient, audioUrl);
  } else {
    plainClient.setTimeout(3000);
    http.begin(plainClient, audioUrl);
  }
  http.setTimeout(5000);

  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("X-Device-Id", DEVICE_ID);

  int httpCode = http.POST((uint8_t*)audioBuffer, audioBufferIdx * sizeof(int16_t));
  if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
    Serial.printf("[YAMNet AUDIO] Transmitted %d samples (HTTP %d)\n", audioBufferIdx, httpCode);
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
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
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
      // INMP441 provides 24-bit audio in high bits of 32-bit slot
      int32_t sample = raw_samples[i] >> 14;
      int32_t abs_sample = abs(sample);

      if (abs_sample > windowPeak) {
        windowPeak = abs_sample;
      }
      windowSumSquares += (double)sample * (double)sample;

      // Accumulate raw audio samples for local YAMNet classification
      if (audioBufferIdx < AUDIO_BUFFER_SAMPLES) {
        audioBuffer[audioBufferIdx++] = (int16_t)constrain(sample, -32768, 32767);
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

      // Edge Pitch Analysis for Infant Cry Detection (350 Hz - 680 Hz)
      float periodicity = 0.0f;
      float pitch = 0.0f;
      if (soundLevel >= 50.0 && audioBufferIdx >= 512) {
        pitch = detectInfantCryPitch(audioBuffer, audioBufferIdx, SAMPLE_RATE, &periodicity);
      }

      const char* classification = "QUIET";
      float confidence = 0.95f;

      if (pitch >= 350.0f && pitch <= 680.0f && soundLevel >= 50.0f) {
        // High harmonic pitch + voiced periodicity matches infant crying
        classification = "POSSIBLE_CRYING";
        confidence = 0.88f;
        Serial.printf("[ACOUSTIC MATCH] 🚨 INFANT CRY DETECTED! Pitch: %.1f Hz | Periodicity: %.2f\n", pitch, periodicity);
      } else if (soundLevel >= 65.0f) {
        classification = "HIGH_SOUND_ACTIVITY";
        confidence = 0.85f;
        Serial.printf("[ACOUSTIC MATCH] 🔊 HIGH SOUND ACTIVITY (Pitch: %.1f Hz)\n", pitch);
      } else if (soundLevel >= 45.0f) {
        classification = "MODERATE_SOUND";
        confidence = 0.75f;
      } else {
        classification = "QUIET";
        confidence = 0.95f;
      }

      // Print to Serial for local monitoring
      Serial.printf("[SOUND] Level: %5.1f dB | RMS: %6.1f | Peak: %5d | STATUS: [%s]\n", soundLevel, rms, windowPeak, classification);

      // Transmit to FastAPI backend with classification & pitch
      sendTelemetryToBackend(soundLevel, rms, windowPeak, classification, pitch, confidence);

      // Reset window accumulators
      windowSumSquares = 0.0;
      windowPeak = 0;
      windowSamplesCount = 0;
    }
  }

  // 4. Periodic Audio Sample Stream for YAMNet Neural Classification (every 2500 ms)
  if (now - lastAudioTransmitTime >= AUDIO_CHUNK_INTERVAL_MS) {
    lastAudioTransmitTime = now;
    sendAudioChunkToBackend();
  }
}
