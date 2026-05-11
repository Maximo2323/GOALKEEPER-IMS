/**
 * @file main.cpp
 * @brief Test sketch — stepper + joystick + range-sensor cross-check.
 *
 * Behavior:
 *   1. Homes the goalkeeper axis (stepper position -> 0 at limit switch).
 *   2. Resets the range-sensor filter so it adopts the fresh zero cleanly.
 *   3. Joystick takes over (proportional speed; driver disabled in deadband).
 *   4. RangeSensor runs every loop: when the axis is idle and its filtered
 *      reading disagrees with the stepper position by more than
 *      RANGE_CORRECT_THRESHOLD_MM, it silently re-zeros the stepper to the
 *      sensor reading.
 *   5. Status print every 500 ms shows both estimates side-by-side so you
 *      can watch the cross-check work.
 *
 * Wiring (Arduino Uno):
 *   D3  STEP   |  D4  DIR   |  D12 ENA   |  D5  LIMIT (NC -> GND)
 *   A0  Joystick X
 *   D11 US TRIG | D13 US ECHO   (only used if RANGE_SENSOR_TYPE = RANGE_ULTRASONIC)
 *   SDA/SCL     ToF             (only used if RANGE_SENSOR_TYPE = RANGE_TOF)
 */

#include <Arduino.h>
#if RANGE_SENSOR_TYPE == RANGE_TOF
#include <Wire.h>
#endif

#include "constants.h"
#include "StepperAxis.h"
#include "JoystickAxis.h"
#include "RangeSensor.h"

// -----------------------------------------------------------------------------
// Hardware objects
// -----------------------------------------------------------------------------
StepperAxis goalkeeper(GK_STEP_PIN, GK_DIR_PIN, GK_LIMIT_PIN,
                       GK_STEPS_PER_MM, GK_AXIS_LENGTH_MM,
                       GK_MAX_SPEED, GK_ACCELERATION,
                       GK_ENA_PIN);

JoystickAxis joystick(JOY_PIN, goalkeeper,
                      JOY_DEADBAND, JOY_MAX_SPEED, JOY_UPDATE_MS);

RangeSensor  range(goalkeeper);

// -----------------------------------------------------------------------------
// Setup
// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    Serial.println(F("\n=== Goalkeeper test: stepper + joystick + range ==="));

#if RANGE_SENSOR_TYPE == RANGE_TOF
    Wire.begin();
    Serial.println(F("[RANGE] Sensor type: ToF"));
#else
    Serial.println(F("[RANGE] Sensor type: Ultrasonic (HC-SR04)"));
#endif

#if RANGE_SENSOR_MOUNT == MOUNT_HOME_END
    Serial.println(F("[RANGE] Mount: HOME end"));
#else
    Serial.println(F("[RANGE] Mount: FAR end"));
#endif

    if (!range.begin()) {
        Serial.println(F("[RANGE] Sensor init FAILED — continuing without cross-check"));
    }

    goalkeeper.init();
    goalkeeper.home();
}

// -----------------------------------------------------------------------------
// Loop
// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();

    // Detect the moment homing finishes -> reset the EMA so it adopts the
    // fresh, known-good zero instead of dragging a stale average through it.
    static AxisState prevState = AxisState::UNINIT;
    AxisState curState = goalkeeper.getState();
    if (prevState != AxisState::HOMED && curState == AxisState::HOMED) {
        range.resetFilter();
        Serial.println(F("[RANGE] Filter reset after homing"));
    }
    prevState = curState;

    if (goalkeeper.isHomed()) {
        joystick.update();
    }

    range.update();   // safe to call always; only acts when homed + idle

    // ---- periodic status print -------------------------------------------
    static unsigned long lastPrint = 0;
    unsigned long now = millis();
    if (now - lastPrint >= 500) {
        lastPrint = now;
        Serial.print(F("[STATUS] "));
        Serial.print(goalkeeper.stateStr());
        Serial.print(F(" stepper="));
        Serial.print(goalkeeper.getPositionMm(), 1);
        Serial.print(F("mm  range="));
        if (range.hasValidReading()) {
            Serial.print(range.getPositionMm(), 1);
            Serial.print(F("mm (raw "));
            Serial.print(range.getRawMm(), 0);
            Serial.print(F(")"));
        } else {
            Serial.print(F("---"));
        }
        Serial.print(F("  defl="));
        Serial.print(joystick.getDeflection(), 2);
        Serial.print(F("  ena="));
        Serial.print(goalkeeper.isEnabled() ? "ON" : "OFF");
        if (goalkeeper.limitTriggered()) Serial.print(F("  [LIMIT]"));
        Serial.println();
    }
}