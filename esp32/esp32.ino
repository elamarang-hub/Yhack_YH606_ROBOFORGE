#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <driver/i2s.h>

// =====================================================
// SMART DOOR SECURITY - ESP32
// =====================================================

// -----------------------------
// VL53L0X 
// -----------------------------
#define TOF_SDA 21
#define TOF_SCL 22

// -----------------------------
// ACTIVE-LOW BUZZER
// -----------------------------
#define BUZZER_PIN 4

// -----------------------------
// INMP441 MICROPHONE - I2S0
// -----------------------------
#define MIC_I2S I2S_NUM_0

#define MIC_SD   32
#define MIC_WS   25
#define MIC_SCK  33

// -----------------------------
// MAX98357A SPEAKER - I2S1
// -----------------------------
#define SPK_I2S I2S_NUM_1   

#define SPK_DIN  14
#define SPK_BCLK 26
#define SPK_LRC  27

// -----------------------------
// SETTINGS
// -----------------------------
#define SERIAL_BAUD 115200
#define SAMPLE_RATE 16000

Adafruit_VL53L0X tof;

bool tofReady = false;
bool micReady = false;
bool speakerReady = false;


// =====================================================
// BUZZER
// =====================================================

void buzzerON()
{
  // ACTIVE-LOW
  digitalWrite(BUZZER_PIN, LOW);
}

void buzzerOFF()
{
  // ACTIVE-LOW
  digitalWrite(BUZZER_PIN, HIGH);
}


// =====================================================
// MICROPHONE SETUP
// =====================================================

void setupMicrophone()
{
  i2s_config_t config = {
    .mode = (i2s_mode_t)(
      I2S_MODE_MASTER |
      I2S_MODE_RX
    ),

    .sample_rate = SAMPLE_RATE,

    .bits_per_sample =
      I2S_BITS_PER_SAMPLE_32BIT,

    .channel_format =
      I2S_CHANNEL_FMT_ONLY_LEFT,

    .communication_format =
      I2S_COMM_FORMAT_I2S,

    .intr_alloc_flags =
      ESP_INTR_FLAG_LEVEL1,

    .dma_buf_count = 8,

    .dma_buf_len = 256,

    .use_apll = false,

    .tx_desc_auto_clear = false,

    .fixed_mclk = 0
  };

  i2s_pin_config_t pins = {
    .bck_io_num = MIC_SCK,
    .ws_io_num = MIC_WS,

    .data_out_num =
      I2S_PIN_NO_CHANGE,

    .data_in_num = MIC_SD
  };

  esp_err_t result =
    i2s_driver_install(
      MIC_I2S,
      &config,
      0,
      NULL
    );

  if (result != ESP_OK)
  {
    Serial.println("MIC_ERROR");
    return;
  }

  result =
    i2s_set_pin(
      MIC_I2S,
      &pins
    );

  if (result != ESP_OK)
  {
    Serial.println("MIC_PIN_ERROR");
    return;
  }

  i2s_zero_dma_buffer(MIC_I2S);

  micReady = true;

  Serial.println("MIC_OK");
}


// =====================================================
// SPEAKER SETUP
// =====================================================

void setupSpeaker()
{
  i2s_config_t config = {

    .mode = (i2s_mode_t)(
      I2S_MODE_MASTER |
      I2S_MODE_TX
    ),

    .sample_rate = SAMPLE_RATE,

    .bits_per_sample =
      I2S_BITS_PER_SAMPLE_16BIT,

    .channel_format =
      I2S_CHANNEL_FMT_RIGHT_LEFT,

    .communication_format =
      I2S_COMM_FORMAT_I2S,

    .intr_alloc_flags =
      ESP_INTR_FLAG_LEVEL1,

    .dma_buf_count = 8,

    .dma_buf_len = 256,

    .use_apll = false,

    .tx_desc_auto_clear = true,

    .fixed_mclk = 0
  };

  i2s_pin_config_t pins = {

  .mck_io_num = I2S_PIN_NO_CHANGE,

  .bck_io_num = SPK_BCLK,

  .ws_io_num = SPK_LRC,

  .data_out_num = SPK_DIN,

  .data_in_num = I2S_PIN_NO_CHANGE
};

  esp_err_t result =
    i2s_driver_install(
      SPK_I2S,
      &config,
      0,
      NULL
    );

  if (result != ESP_OK)
  {
    Serial.println("SPEAKER_ERROR");
    return;
  }

  result =
    i2s_set_pin(
      SPK_I2S,
      &pins
    );

  if (result != ESP_OK)
  {
    Serial.println("SPEAKER_PIN_ERROR");
    return;
  }

  i2s_zero_dma_buffer(SPK_I2S);

  speakerReady = true;

  Serial.println("SPEAKER_OK");
}


// =====================================================
// TOF DISTANCE
// =====================================================

void readDistance()
{
  if (!tofReady)
    return;

  VL53L0X_RangingMeasurementData_t measurement;

  tof.rangingTest(
    &measurement,
    false
  );

  if (measurement.RangeStatus == 4)
  {
    Serial.println("DIST_INVALID");
    return;
  }

  uint16_t mm =
    measurement.RangeMilliMeter;

  Serial.print("DIST:");
  Serial.println(mm);
}


// =====================================================
// MICROPHONE TEST LEVEL
// =====================================================

void microphoneLevel()
{
  if (!micReady)
  {
    Serial.println("MIC_NOT_READY");
    return;
  }

  int32_t buffer[256];

  size_t bytesRead = 0;

  esp_err_t result =
    i2s_read(
      MIC_I2S,
      buffer,
      sizeof(buffer),
      &bytesRead,
      100 / portTICK_PERIOD_MS
    );

  if (result != ESP_OK ||
      bytesRead == 0)
  {
    Serial.println("MIC_READ_ERROR");
    return;
  }

  int samples =
    bytesRead / sizeof(int32_t);

  long long total = 0;

  for (int i = 0; i < samples; i++)
  {
    int32_t sample =
      buffer[i] >> 14;

    total += abs(sample);
  }

  long average =
    total / samples;

  Serial.print("MIC_LEVEL:");
  Serial.println(average);
}


// =====================================================
// COMMAND PROCESSING
// =====================================================

void processCommand(String command)
{
  command.trim();

  // -----------------------------
  // PING
  // -----------------------------

  if (command == "PING")
  {
    Serial.println("PONG");
  }

  // -----------------------------
  // STATUS
  // -----------------------------

  else if (command == "STATUS")
  {
    Serial.println("ESP32:OK");

    Serial.print("TOF:");
    Serial.println(
      tofReady ? "OK" : "ERROR"
    );

    Serial.print("MIC:");
    Serial.println(
      micReady ? "OK" : "ERROR"
    );

    Serial.print("SPEAKER:");
    Serial.println(
      speakerReady ? "OK" : "ERROR"
    );

    Serial.println("BUZZER:ACTIVE_LOW");
  }

  // -----------------------------
  // BUZZER
  // -----------------------------

  else if (command == "BUZZER_ON")
  {
    buzzerON();
    Serial.println("BUZZER:ON");
  }

  else if (command == "BUZZER_OFF")
  {
    buzzerOFF();
    Serial.println("BUZZER:OFF");
  }

  // -----------------------------
  // MIC
  // -----------------------------

  else if (command == "MIC_TEST")
  {
    Serial.println("MIC_TEST");

    for (int i = 0; i < 20; i++)
    {
      microphoneLevel();
      delay(100);
    }

    Serial.println("MIC_TEST_END");
  }

  // -----------------------------
  // GREETING
  // -----------------------------

  else if (command == "GREETING")
  {
    Serial.println("GREETING_REQUEST");
  }

  // -----------------------------
  // UNKNOWN
  // -----------------------------

  else
  {
    Serial.print("UNKNOWN_COMMAND:");
    Serial.println(command);
  }
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(SERIAL_BAUD);

  delay(1000);

  Serial.println();
  Serial.println(
    "================================"
  );
  Serial.println(
    " SMART DOOR SECURITY ESP32"
  );
  Serial.println(
    "================================"
  );

  // -----------------------------
  // BUZZER
  // -----------------------------

  pinMode(
    BUZZER_PIN,
    OUTPUT
  );

  // ACTIVE-LOW
  // HIGH = OFF
  buzzerOFF();

  Serial.println("BUZZER_OK");

  // -----------------------------
  // I2C / TOF
  // -----------------------------

  Wire.begin(
    TOF_SDA,
    TOF_SCL
  );

  if (!tof.begin())
  {
    Serial.println("TOF_ERROR");

    tofReady = false;
  }
  else
  {
    Serial.println("TOF_OK");

    tofReady = true;
  }

  // -----------------------------
  // AUDIO
  // -----------------------------

  setupMicrophone();

  setupSpeaker();

  // -----------------------------
  // READY
  // -----------------------------

  Serial.println(
    "================================"
  );

  Serial.println(
    "ESP32_READY"
  );

  Serial.println(
    "================================"
  );
}


// =====================================================
// MAIN LOOP
// =====================================================

void loop()
{
  // -----------------------------
  // SERIAL COMMANDS
  // -----------------------------

  if (Serial.available())
  {
    String command =
      Serial.readStringUntil('\n');

    processCommand(command);
  }

  // -----------------------------
  // DISTANCE
  // -----------------------------

  static unsigned long lastDistance =
    0;

  if (millis() - lastDistance >= 100)
  {
    lastDistance = millis();

    readDistance();
  }

  delay(5);
}