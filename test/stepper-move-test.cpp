/**
 * @file stepper-move-test.cpp
 * @brief Minimal stepper move test: forward, back, wait 1s, repeat.
 */

#include <Arduino.h>
#include <AccelStepper.h>
#include "pins.h"

static constexpr long  MOVE_STEPS   = 400;
static constexpr float MAX_SPEED    = 600.0f;
static constexpr float ACCELERATION = 900.0f;

AccelStepper stepper(AccelStepper::DRIVER, GK_STEP_PIN, GK_DIR_PIN);

void setup() {
    pinMode(GK_ENA_PIN, OUTPUT);
    digitalWrite(GK_ENA_PIN, LOW);   // enable driver (active-LOW)

    stepper.setMaxSpeed(MAX_SPEED);
    stepper.setAcceleration(ACCELERATION);
    Serial.begin(115200);
}

void loop() {
    digitalWrite(GK_ENA_PIN, LOW);  // disable driver (active-LOW)
    stepper.moveTo(MOVE_STEPS); 
    while (stepper.distanceToGo() != 0) {
        stepper.run();
    }
    Serial.print(F("Moved to ")); Serial.println(stepper.currentPosition());

    stepper.moveTo(0);
    while (stepper.distanceToGo() != 0) {
        stepper.run();
    }
    Serial.print(F("Moved to ")); Serial.println(stepper.currentPosition());

    digitalWrite(GK_ENA_PIN, HIGH);  // disable driver (active-LOW)
    delay(1000);
}
