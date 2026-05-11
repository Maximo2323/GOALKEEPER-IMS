/**
 * @file test_full_bench.cpp
 * @brief Bench test of the full I/O surface, no motor / no solenoid coil.
 *
 * Exercises:
 *   - Stepper driver pins (STEP, DIR, ENA) via LEDs
 *   - Solenoid output pin via LED (no MOSFET, no coil)
 *   - Joystick proportional speed control
 *   - Two limit-switch buttons (HOME and FAR)
 *   - Fire button -> solenoid pulse + cooldown
 *   - Real homing routine using the HOME button
 *
 * =============================================================================
 *                        WIRING (Arduino Uno)
 * =============================================================================
 *
 *  LEDs (each: pin -> LED anode, cathode -> 330R -> GND):
 *    D3  STEP        -> LED   (flickers when stepping; faster = more deflection)
 *    D4  DIR         -> LED   (solid HIGH or LOW depending on direction)
 *    D12 ENA         -> LED   (ON solid when driver enabled — note: active LOW
 *                              so the LED lights when the pin is LOW. To make
 *                              this work with a "pin -> LED -> R -> GND" wiring,
 *                              instead wire ENA's LED as: 5V -> 330R -> LED -> D12.
 *                              Then LED on = pin LOW = driver enabled.)
 *    D9  SOLENOID    -> LED   (active HIGH — wire normally: D9 -> LED -> 330R -> GND)
 *
 *  BUTTONS (each: pin -> button -> GND. INPUT_PULLUP enabled in code, so
 *           pressed = LOW):
 *    D5  HOME LIMIT  -> button -> GND   (simulates carriage hitting home end)
 *    A3  FAR  LIMIT  -> button -> GND   (simulates carriage hitting far end)
 *    A1  FIRE        -> button -> GND   (one press = one kick)
 *
 *  JOYSTICK:
 *    A0  X axis      (0..1023, center ~512)
 *    5V, GND         to joystick power
 *
 * =============================================================================
 *                       EXPECTED BEHAVIOR
 * =============================================================================
 *
 *   Boot -> "[AXIS] Homing started..."  STEP LED flickers (slow homing speed),
 *           ENA LED ON, DIR LED in homing direction.
 *
 *   Press HOME button briefly -> homing detects "limit", BACKOFF (small move),
 *                                state -> HOMED. STEP LED stops.
 *
 *   Joystick deflection -> ENA on, DIR follows sign, STEP flickers
 *                          proportional to deflection magnitude.
 *
 *   Center joystick -> ENA off after deceleration, STEP stops.
 *
 *   Press HOME button mid-move toward home -> FAULT (axis stops, must reset).
 *   Press FAR  button mid-move away from home -> FAULT.
 *   Press FIRE button -> SOLENOID LED pulses ~50 ms, then cooldown ~800 ms.
 *
 *   Send 'r' over Serial -> clears FAULT and re-homes.
 *
 * =============================================================================
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "StepperAxis.h"
#include "JoystickAxis.h"
#include "Solenoid.h"

// Cap top speed so STEP LED is visibly flickering (real GK_MAX_SPEED would
// look like a steady glow at 3 kHz).
static constexpr float TEST_MAX_SPEED = 250.0f;

// -----------------------------------------------------------------------------
// Hardware objects
// -----------------------------------------------------------------------------
StepperAxis goalkeeper(GK_STEP_PIN, GK_DIR_PIN,
                       GK_LIMIT_HOME_PIN,
                       GK_STEPS_PER_MM, GK_AXIS_LENGTH_MM,
                       GK_MAX_SPEED, GK_ACCELERATION,
                       GK_ENA_PIN,
                       GK_LIMIT_FAR_PIN);   // <-- new: far limit wired in

JoystickAxis joystick(JOY_PIN, goalkeeper,
                      JOY_DEADBAND, TEST_MAX_SPEED, JOY_UPDATE_MS);

Solenoid     kicker;   // uses pins.h defaults: D9 / A1

// -----------------------------------------------------------------------------
// Setup
// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    Serial.println(F("\n=== FULL BENCH TEST ==="));
    Serial.println(F("Pins:"));
    Serial.print  (F("  STEP        D")); Serial.println(GK_STEP_PIN);
    Serial.print  (F("  DIR         D")); Serial.println(GK_DIR_PIN);
    Serial.print  (F("  ENA         D")); Serial.println(GK_ENA_PIN);
    Serial.print  (F("  HOME limit  D")); Serial.println(GK_LIMIT_HOME_PIN);
    Serial.print  (F("  FAR  limit  A")); Serial.println(GK_LIMIT_FAR_PIN - A0);
    Serial.print  (F("  Joystick X  A")); Serial.println(JOY_PIN - A0);
    Serial.print  (F("  Solenoid    D")); Serial.println(SOL_MOSFET_PIN);
    Serial.print  (F("  Fire btn    A")); Serial.println(SOL_BUTTON_PIN - A0);
    Serial.println();
    Serial.print  (F("Test top speed: ")); Serial.print(TEST_MAX_SPEED);
    Serial.println(F(" steps/sec"));
    Serial.println();

    goalkeeper.init();
    kicker.begin();

    Serial.println(F("Send 'r' to clear FAULT and re-home."));
    Serial.println(F("Send 'h' to start homing again."));
    Serial.println(F("Send 'p' to skip homing (pretend HOMED at 0)."));
    Serial.println();

    goalkeeper.home();   // start the real homing routine; press HOME btn to "trigger" it
}

// -----------------------------------------------------------------------------
// Loop
// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();
    kicker.update();

    if (goalkeeper.isHomed()) {
        joystick.update();
    }

    // ---- serial commands ------------------------------------------------
    if (Serial.available()) {
        char c = Serial.read();
        if (c == 'r') {
            goalkeeper.clearFault();
            goalkeeper.home();
        } else if (c == 'h') {
            goalkeeper.home();
        } else if (c == 'p') {
            goalkeeper.setHomedPretend();
            Serial.println(F("[AXIS] Pretending HOMED at 0 mm"));
        }
    }

    // ---- state-transition logging --------------------------------------
    static AxisState lastState = AxisState::UNINIT;
    AxisState cur = goalkeeper.getState();
    if (cur != lastState) {
        Serial.print(F("[AXIS] "));
        Serial.print(goalkeeper.stateStr());
        Serial.println();
        lastState = cur;
    }

    // ---- periodic status print -----------------------------------------
    static unsigned long lastPrint = 0;
    unsigned long now = millis();
    if (now - lastPrint >= 400) {
        lastPrint = now;
        Serial.print(F("[STATUS] "));
        Serial.print(goalkeeper.stateStr());
        Serial.print(F("  pos="));
        Serial.print(goalkeeper.getPositionMm(), 1);
        Serial.print(F("mm  defl="));
        Serial.print(joystick.getDeflection(), 2);
        Serial.print(F("  ena="));
        Serial.print(goalkeeper.isEnabled() ? "ON " : "off");
        Serial.print(F("  HOME="));
        Serial.print(goalkeeper.homeLimitTriggered() ? "PRESSED" : "open   ");
        Serial.print(F("  FAR="));
        Serial.print(goalkeeper.farLimitTriggered()  ? "PRESSED" : "open   ");
        Serial.print(F("  KICK="));
        switch (kicker.getState()) {
            case SolenoidState::IDLE:     Serial.print(F("ready"));   break;
            case SolenoidState::FIRING:   Serial.print(F("FIRING"));  break;
            case SolenoidState::COOLDOWN: Serial.print(F("cooling")); break;
        }
        Serial.println();
    }
}