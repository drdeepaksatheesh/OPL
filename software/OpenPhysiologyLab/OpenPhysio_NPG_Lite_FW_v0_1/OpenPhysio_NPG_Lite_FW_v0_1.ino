// ============================================================
// OpenPhysio NPG Lite Universal Serial Firmware v0.1
// For ECG / EMG / EEG / EOG raw acquisition experiments
//
// Commands over Serial:
// WHOAREYOU
// STATUS
// HELP
// SETRATE 250
// SETRATE 500
// SETRATE 1000
// SETCH 1
// SETCH 2
// SETCH 3
// SETCH 4
// SETCH 5
// SETCH 6
// START
// STOP
//
// Data format:
// sample,time_us,ch1,ch2,ch3,ch4,ch5,ch6
//
// Notes:
// - Always outputs 6 channel columns.
// - Inactive channels are left as blank fields.
// - Raw ADC values are streamed.
// - Default: 500 Hz, 1 channel.
// ============================================================

#define BAUD_RATE 230400

// ============================================================
// CHANNEL PIN DEFINITIONS
// ============================================================
// These are intentionally kept simple.
// If compilation fails because A3/A4/A5 are not defined,
// we will replace them with the exact GPIO pins for your NPG Lite board.

#define CH1_PIN A0
#define CH2_PIN A1
#define CH3_PIN A2
#define CH4_PIN A3
#define CH5_PIN A4
#define CH6_PIN A5

// ============================================================
// FIRMWARE INFO
// ============================================================

String firmwareName = "OpenPhysio_NPG_Lite_FW";
String firmwareVersion = "0.1";

// ============================================================
// ACQUISITION SETTINGS
// ============================================================

bool streaming = false;

unsigned long sampleNumber = 0;

int sampleRate = 500;
int channelCount = 1;

unsigned long sampleIntervalMicros = 1000000UL / 500;
unsigned long nextSampleTime = 0;

String commandBuffer = "";

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(BAUD_RATE);
  delay(2000);

  analogReadResolution(12);

  sampleIntervalMicros = 1000000UL / sampleRate;
  nextSampleTime = micros();

  Serial.println("OpenPhysio NPG Lite Firmware Ready");
  Serial.println("Type HELP for commands");
}

// ============================================================
// MAIN LOOP
// ============================================================

void loop() {
  readSerialCommand();

  if (streaming) {
    streamSamples();
  }
}

// ============================================================
// READ SERIAL COMMANDS
// ============================================================

void readSerialCommand() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      commandBuffer.trim();

      if (commandBuffer.length() > 0) {
        handleCommand(commandBuffer);
      }

      commandBuffer = "";
    } else {
      commandBuffer += c;
    }
  }
}

// ============================================================
// HANDLE COMMANDS
// ============================================================

void handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "WHOAREYOU") {
    Serial.print("DEVICE,");
    Serial.print(firmwareName);
    Serial.print(",");
    Serial.println(firmwareVersion);
  }

  else if (cmd == "STATUS") {
    Serial.print("STATUS,");
    Serial.print("streaming=");
    Serial.print(streaming ? "1" : "0");
    Serial.print(",");
    Serial.print("sample_rate=");
    Serial.print(sampleRate);
    Serial.print(",");
    Serial.print("channels=");
    Serial.print(channelCount);
    Serial.print(",");
    Serial.print("baud=");
    Serial.println(BAUD_RATE);
  }

  else if (cmd == "START") {
    sampleNumber = 0;
    nextSampleTime = micros();
    streaming = true;

    Serial.println("STARTED");
    Serial.println("sample,time_us,ch1,ch2,ch3,ch4,ch5,ch6");
  }

  else if (cmd == "STOP") {
    streaming = false;
    Serial.println("STOPPED");
  }

  else if (cmd.startsWith("SETRATE")) {
    int spaceIndex = cmd.indexOf(' ');

    if (spaceIndex > 0) {
      int newRate = cmd.substring(spaceIndex + 1).toInt();

      if (newRate == 250 || newRate == 500 || newRate == 1000) {
        sampleRate = newRate;
        sampleIntervalMicros = 1000000UL / sampleRate;

        Serial.print("OK,SETRATE,");
        Serial.println(sampleRate);
      } else {
        Serial.println("ERROR,Allowed rates: 250, 500, 1000");
      }
    } else {
      Serial.println("ERROR,Use SETRATE 500");
    }
  }

  else if (cmd.startsWith("SETCH")) {
    int spaceIndex = cmd.indexOf(' ');

    if (spaceIndex > 0) {
      int newChannelCount = cmd.substring(spaceIndex + 1).toInt();

      if (newChannelCount >= 1 && newChannelCount <= 6) {
        channelCount = newChannelCount;

        Serial.print("OK,SETCH,");
        Serial.println(channelCount);
      } else {
        Serial.println("ERROR,Channels must be 1 to 6");
      }
    } else {
      Serial.println("ERROR,Use SETCH 1 or SETCH 6");
    }
  }

  else if (cmd == "HELP") {
    Serial.println("COMMANDS:");
    Serial.println("WHOAREYOU");
    Serial.println("STATUS");
    Serial.println("START");
    Serial.println("STOP");
    Serial.println("SETRATE 250");
    Serial.println("SETRATE 500");
    Serial.println("SETRATE 1000");
    Serial.println("SETCH 1");
    Serial.println("SETCH 2");
    Serial.println("SETCH 3");
    Serial.println("SETCH 4");
    Serial.println("SETCH 5");
    Serial.println("SETCH 6");
    Serial.println("HELP");
  }

  else {
    Serial.print("ERROR,Unknown command: ");
    Serial.println(cmd);
  }
}

// ============================================================
// STREAM SAMPLES
// ============================================================

void streamSamples() {
  unsigned long now = micros();

  if ((long)(now - nextSampleTime) >= 0) {
    nextSampleTime += sampleIntervalMicros;

    int ch1 = 0;
    int ch2 = 0;
    int ch3 = 0;
    int ch4 = 0;
    int ch5 = 0;
    int ch6 = 0;

    if (channelCount >= 1) {
      ch1 = analogRead(CH1_PIN);
    }

    if (channelCount >= 2) {
      ch2 = analogRead(CH2_PIN);
    }

    if (channelCount >= 3) {
      ch3 = analogRead(CH3_PIN);
    }

    if (channelCount >= 4) {
      ch4 = analogRead(CH4_PIN);
    }

    if (channelCount >= 5) {
      ch5 = analogRead(CH5_PIN);
    }

    if (channelCount >= 6) {
      ch6 = analogRead(CH6_PIN);
    }

    Serial.print(sampleNumber);
    Serial.print(",");
    Serial.print(now);
    Serial.print(",");

    if (channelCount >= 1) Serial.print(ch1);
    Serial.print(",");

    if (channelCount >= 2) Serial.print(ch2);
    Serial.print(",");

    if (channelCount >= 3) Serial.print(ch3);
    Serial.print(",");

    if (channelCount >= 4) Serial.print(ch4);
    Serial.print(",");

    if (channelCount >= 5) Serial.print(ch5);
    Serial.print(",");

    if (channelCount >= 6) Serial.print(ch6);

    Serial.println();

    sampleNumber++;
  }
}