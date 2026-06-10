/**
 * @file solenoidburst.cpp
 * @brief Fires the solenoid 4 times, waits, repeats. No button.
 *
 * Uses Solenoid library + constants.h timing (SOL_PULSE_MS, SOL_COOLDOWN_MS).
 * Wiring: D9 -> MOSFET gate (or D9 -> LED -> 330R -> GND for bench).
 */

#include <Arduino.h>
#include "constants.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Tunables
// -----------------------------------------------------------------------------
static const uint8_t       KICKS_PER_BURST = 4;
static const unsigned long REST_BETWEEN_BURSTS_MS = 3000;   // <-- "x amount of time"

// -----------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------
Solenoid kicker(SOL_MOSFET_PIN, 255);   // 255 = no button
uint8_t       kickCount  = 0;
unsigned long restUntil  = 0;

void setup() {
    Serial.begin(SERIAL_BAUD);
    kicker.begin();
    Serial.println(F("\n=== BURST TEST: 4 kicks, rest, repeat ==="));
}

void loop() {
    kicker.update();

    if (millis() < restUntil) return;   // resting between bursts

    if (kicker.canFire()) {
        kicker.fire();
        kickCount++;
        Serial.print(F("kick ")); Serial.println(kickCount);

        if (kickCount >= KICKS_PER_BURST) {
            kickCount = 0;
            // wait for the last pulse + cooldown to finish, then rest
            restUntil = millis() + SOL_PULSE_MS + SOL_COOLDOWN_MS + REST_BETWEEN_BURSTS_MS;
            Serial.print(F("resting "));
            Serial.print(REST_BETWEEN_BURSTS_MS);
            Serial.println(F(" ms..."));
        }
    }
}
