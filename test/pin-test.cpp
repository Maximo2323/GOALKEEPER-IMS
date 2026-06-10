/**
 * @file pin-test.cpp
 * @brief Raw pin diagnostic — reads every input directly, no libraries.
 *
 * Just pinMode + digitalRead + analogRead printed every 200 ms. Use this
 * first to confirm the Arduino is physically seeing your button / switch /
 * joystick activity before debugging higher-level code.
 *
 * Pin layout (matches include/pins.h):
 *   D5  BTN_FIRE     fire button
 *   D6  BTN_MODE     mode toggle
 *   D7  GK_LIMIT_HOME limit switch
 *   D8  GK_LIMIT_FAR  limit switch
 *   A0  JOY          joystick X (analog)
 *
 *   D2  ENA, D3 STEP, D4 DIR, D9 SOL — outputs, held LOW (driver disabled,
 *   solenoid off) so the bench circuit is quiet while you read inputs.
 *
 * WHAT TO LOOK FOR (with current INPUT_PULLUP config, switches to GND):
 *   - Idle  -> pin reads 1 (HIGH)
 *   - Pressed/triggered -> pin reads 0 (LOW)
 *   If your switches are wired to VCC instead of GND the polarity will be
 *   inverted; the raw 0/1 column tells you what the pin actually sees,
 *   independent of the constants.h LIMIT_TRIGGERED setting.
 *
 *   Joystick:
 *   - Center    -> ~512 (varies module to module)
 *   - Full left -> near 0
 *   - Full right-> near 1023
 */

#include <Arduino.h>
#include "pins.h"

static constexpr unsigned long REPORT_MS = 200;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 2000) {}

    // ---- Inputs: external pull-down resistors to GND, button/switch to VCC --
    pinMode(BTN_FIRE_PIN,      INPUT);
    pinMode(BTN_MODE_PIN,      INPUT);
    pinMode(GK_LIMIT_HOME_PIN, INPUT);
    pinMode(GK_LIMIT_FAR_PIN,  INPUT);

    // ---- Outputs: parked LOW so the bench circuit is quiet ------------------
    pinMode(GK_STEP_PIN,    OUTPUT); digitalWrite(GK_STEP_PIN,    LOW);
    pinMode(GK_DIR_PIN,     OUTPUT); digitalWrite(GK_DIR_PIN,     LOW);
    pinMode(GK_ENA_PIN,     OUTPUT); digitalWrite(GK_ENA_PIN,     HIGH); // active-LOW -> disabled
    pinMode(SOL_MOSFET_PIN, OUTPUT); digitalWrite(SOL_MOSFET_PIN, LOW);

    Serial.println(F("\n=== RAW PIN DIAGNOSTIC ==="));
    Serial.println(F("Pull-down wiring: idle reads 0, active reads 1"));
    Serial.println();
    Serial.println(F("         FIRE  MODE  HOME  FAR   JOY"));
    Serial.println(F("         D5    D6    D7    D8    A0"));
}

void loop() {
    static unsigned long last = 0;
    if (millis() - last < REPORT_MS) return;
    last = millis();

    const int fire = digitalRead(BTN_FIRE_PIN);
    const int mode = digitalRead(BTN_MODE_PIN);
    const int home = digitalRead(GK_LIMIT_HOME_PIN);
    const int far  = digitalRead(GK_LIMIT_FAR_PIN);
    const int joy  = analogRead(JOY_PIN);

    Serial.print(F("         "));
    Serial.print(fire); Serial.print(F("     "));
    Serial.print(mode); Serial.print(F("     "));
    Serial.print(home); Serial.print(F("     "));
    Serial.print(far);  Serial.print(F("     "));
    Serial.println(joy);
}
