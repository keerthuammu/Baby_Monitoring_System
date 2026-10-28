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
const char* BACKEND_URL   = "https://baby-monitor-backend-8m8o.onrender.com/api/readings";

// Security API Key (must match API_KEY in backend/.env):
const char* API_KEY       = "baby_monitor_device_secret_key_123";

// Unique Device Identifier:
const char* DEVICE_ID     = "esp32-nursery-01";

// Transmission interval in milliseconds (1000 - 2500 ms recommended):
const unsigned long TRANSMIT_INTERVAL_MS = 1500;

// ==========================================
// 2. I2S MICROPHONE CONFIGURATION
// ==========================================
#define I2S_SCK_PIN       26
#define I2S_WS_PIN        25
#define I2S_SD_PIN        33

#define I2S_PORT          I2S_NUM_0
#define SAMPLE_RATE       16000
#define CHUNK_SIZE        512

// ==========================================
// GLOBAL STATE VARIABLES
// ==========================================
unsigned long lastTransmitTime = 0;
unsigned long lastWifiRetryTime = 0;
bool wifiConnected = false;

// Audio window accumulation
double windowSumSquares = 0.0;
int32_t windowPeak = 0;
unsigned long windowSamplesCount = 0;

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

// Transmit calculated features to FastAPI backend
void sendTelemetryToBackend(float soundLevel, float rms, int peak) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Skipped: Wi-Fi offline. Continuing local sound monitoring.");
    return;
  }

  HTTPClient http;
  String urlStr = String(BACKEND_URL);

  if (urlStr.startsWith("https://")) {
    WiFiClientSecure secureClient;
    secureClient.setInsecure(); // Permits SSL handshake with Render cloud
    http.begin(secureClient, BACKEND_URL);
  } else {
    WiFiClient client;
    http.begin(client, BACKEND_URL);
  }
  http.setTimeout(4000); // 4.0 second timeout for cloud latency

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);

  // Construct JSON payload
  char jsonBuffer[256];
  snprintf(
    jsonBuffer,
    sizeof(jsonBuffer),
    "{\"device_id\":\"%s\",\"sound_level\":%.2f,\"rms_amplitude\":%.2f,\"peak_amplitude\":%d}",
    DEVICE_ID,
    soundLevel,
    rms,
    peak
  );

  int httpCode = http.POST((uint8_t*)jsonBuffer, strlen(jsonBuffer));

  if (httpCode == HTTP_CODE_CREATED || httpCode == HTTP_CODE_OK) {
    Serial.printf("[HTTP 201] Sent -> %.1f dB | RMS: %.1f | Peak: %d\n", soundLevel, rms, peak);
  } else if (httpCode > 0) {
    Serial.printf("[HTTP ERROR] Server responded with code: %d\n", httpCode);
  } else {
    Serial.printf("[HTTP FAILED] Connection failed (%s). Check server IP & Firewall.\n", http.errorToString(httpCode).c_str());
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
  Serial.printf("Transmit Interval: %lu ms\n", TRANSMIT_INTERVAL_MS);

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
    }
    windowSamplesCount += samples_read;
  }

  // 3. Periodic Telemetry Transmission
  unsigned long now = millis();
  if (now - lastTransmitTime >= TRANSMIT_INTERVAL_MS) {
    lastTransmitTime = now;

    if (windowSamplesCount > 0) {
      double rms = sqrt(windowSumSquares / windowSamplesCount);
      // Normalized sound level score (approximate dB SPL mapping)
      double soundLevel = 20.0 * log10(rms > 1.0 ? rms : 1.0);

      // Print to Serial for local monitoring
      Serial.printf("[SOUND] Level: %5.1f dB | RMS: %6.1f | Peak: %5d | ", soundLevel, rms, windowPeak);
      if (soundLevel >= 65.0) {
        Serial.println("STATUS: [HIGH SOUND ACTIVITY / CRYING]");
      } else if (soundLevel >= 45.0) {
        Serial.println("STATUS: [MODERATE SOUND]");
      } else {
        Serial.println("STATUS: [QUIET]");
      }

      // Transmit to FastAPI backend
      sendTelemetryToBackend(soundLevel, rms, windowPeak);

      // Reset window accumulators
      windowSumSquares = 0.0;
      windowPeak = 0;
      windowSamplesCount = 0;
    }
  }
}
