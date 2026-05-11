/**
 * @file test_pins_raw.cpp
 * @brief Raw pin diagnostic — reads every input in the project directly.
 *
 * NO libraries, NO state machines. Just pinMode + digitalRead + analogRead
 * printed every 200 ms. Use this first to confirm the Arduino is physically
 * seeing your button presses before debugging any higher-level code.
 *
 * WHAT TO LOOK FOR:
 *   - Button unpressed -> pin reads HIGH (INPUT_PULLUP holds it up)
 *   - Button pressed   -> pin reads LOW  (button shorts pin to GND)
 *   If a button reads LOW all the time: short to GND somewhere, or wired
 *   directly to GND without a button in series.
 *   If a button reads HIGH even when pressed: button not reaching GND,
 *   wrong pin number, or open connection.
 *
 * WIRING REMINDER — all buttons: pin -> button -> GND. Nothing else.
 *   D5  HOME limit button
 *   A3  FAR  limit button
 *   A1  FIRE button
 *   A0  Joystick X (analog)
 */

#include <Arduino.h>
#include "pins.h"

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 2000) {}

    // Configure all inputs explicitly here — no library involvement.
    pinMode(GK_LIMIT_HOME_PIN, INPUT_PULLUP);
    pinMode(GK_LIMIT_FAR_PIN,  INPUT_PULLUP);
    pinMode(SOL_BUTTON_PIN,    INPUT_PULLUP);

    // Outputs: just set them LOW so they don't drive the bench circuit.
    pinMode(GK_STEP_PIN, OUTPUT); digitalWrite(GK_STEP_PIN, LOW);
    pinMode(GK_DIR_PIN,  OUTPUT); digitalWrite(GK_DIR_PIN,  LOW);
    pinMode(GK_ENA_PIN,  OUTPUT); digitalWrite(GK_ENA_PIN,  HIGH); // disabled
    pinMode(SOL_MOSFET_PIN, OUTPUT); digitalWrite(SOL_MOSFET_PIN, LOW);

    Serial.println(F("\n=== RAW PIN DIAGNOSTIC ==="));
    Serial.println(F("Press buttons and watch the readings change."));
    Serial.println(F("Unpressed = HIGH (1), Pressed = LOW (0)"));
    Serial.println();
    Serial.println(F("         HOME  FAR   FIRE  JOY(raw)"));
    Serial.println(F("         D5    A3    A1    A0"));
}

void loop() {
    static unsigned long last = 0;
    if (millis() - last < 200) return;
    last = millis();

    int home = digitalRead(GK_LIMIT_HOME_PIN);
    int far  = digitalRead(GK_LIMIT_FAR_PIN);
    int fire = digitalRead(SOL_BUTTON_PIN);
    int joy  = analogRead(JOY_PIN);

    Serial.print(F("         "));
    Serial.print(home); Serial.print(F("     "));
    Serial.print(far);  Serial.print(F("     "));
    Serial.print(fire); Serial.print(F("     "));
    Serial.println(joy);
}