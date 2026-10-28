/*
 * INMP441 I2S Microphone Test & Sound Level Monitor
 * 
 * Hardware:
 *   ESP32 DevKit V1
 *   INMP441 I2S Digital MEMS Microphone
 * 
 * Pinout:
 *   SCK (Serial Clock)  -> GPIO 26
 *   WS  (Word Select)   -> GPIO 25
 *   SD  (Serial Data)   -> GPIO 33
 *   VDD                 -> ESP32 3V3 (NEVER connect to 5V!)
 *   GND                 -> ESP32 GND
 *   L/R                 -> ESP32 GND (Selects Left Channel)
 * 
 * Arduino IDE Settings:
 *   Board: "ESP32 Dev Module" (esp32 by Espressif Systems 3.x)
 *   Baud Rate: 115200
 */

#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

// I2S Pin Definitions
#define I2S_SCK_PIN   26
#define I2S_WS_PIN    25
#define I2S_SD_PIN    33

// I2S Port & Audio Config
#define I2S_PORT          I2S_NUM_0
#define SAMPLE_RATE       16000
#define BLOCK_SIZE        512   // Number of samples per chunk

void setupI2S() {
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = BLOCK_SIZE,
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
    Serial.printf("Failed to install I2S driver: %d\n", err);
    while (true) delay(1000);
  }

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("Failed to set I2S pins: %d\n", err);
    while (true) delay(1000);
  }

  Serial.println("INMP441 I2S Microphone initialized successfully.");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n--- INMP441 Microphone Standalone Test ---");
  Serial.println("Testing audio capture and real-time sound amplitude calculation.");
  
  setupI2S();
}

void loop() {
  int32_t raw_samples[BLOCK_SIZE];
  size_t bytes_read = 0;

  esp_err_t result = i2s_read(I2S_PORT, &raw_samples, sizeof(raw_samples), &bytes_read, portMAX_DELAY);

  if (result == ESP_OK && bytes_read > 0) {
    int samples_read = bytes_read / sizeof(int32_t);
    double sum_squares = 0.0;
    int32_t peak_amplitude = 0;

    for (int i = 0; i < samples_read; i++) {
      // INMP441 is 24-bit data in 32-bit slot, shift right by 8 or 14 for scaling
      int32_t sample = raw_samples[i] >> 14; 
      int32_t abs_sample = abs(sample);
      
      if (abs_sample > peak_amplitude) {
        peak_amplitude = abs_sample;
      }
      sum_squares += (double)sample * (double)sample;
    }

    double rms = sqrt(sum_squares / samples_read);
    
    // Normalized sound level score (approximate dB scale representation)
    double sound_level = 20.0 * log10(rms > 1.0 ? rms : 1.0);

    // Print to Serial Monitor and Serial Plotter format
    Serial.print("RMS: ");
    Serial.print(rms, 2);
    Serial.print(" | Peak: ");
    Serial.print(peak_amplitude);
    Serial.print(" | SoundLevel: ");
    Serial.print(sound_level, 2);
    Serial.print(" dB | Status: ");

    if (sound_level > 65.0) {
      Serial.println("HIGH SOUND ACTIVITY");
    } else if (sound_level > 40.0) {
      Serial.println("MODERATE ACTIVITY");
    } else {
      Serial.println("QUIET");
    }
  } else {
    Serial.println("Warning: I2S read error or timeout.");
  }

  delay(200); // 5 updates per second for serial monitoring
}
