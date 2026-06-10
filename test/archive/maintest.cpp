/**
 * @file test_full_bench.cpp
 * @brief Full library integration test on bench hardware.
 *
 * All speeds, accelerations, deadbands, etc. come from constants.h — no
 * overrides in this file. Tune behavior by editing constants.h and reflashing.
 *
 * Hardware on bench:
 *   D2  STEP   -> LED+R
 *   D3  DIR    -> LED+R
 *   D4  ENA    -> LED+R   (active-LOW: LED on = driver enabled)
 *   D5  FIRE   -> button to GND (INPUT_PULLUP)
 *   D9  SOL    -> LED+R
 *   A0  JOY    -> joystick X
 *   A1  HOME   -> button to GND (INPUT_PULLUP)
 *   A2  FAR    -> button to GND (INPUT_PULLUP)
 *
 * Test flow:
 *   1. Boot -> calibration runs automatically:
 *        HOMING_HOME (slow STEP, hunt for HOME) -> press HOME button briefly
 *        BACKOFF_HOME (gentle accelerated move 5 mm out)
 *        HOMING_FAR  (slow STEP toward far) -> press FAR button briefly
 *        BACKOFF_FAR
 *        TO_CENTER   (move to half of measured length, faster)
 *        HOMED       (sitting at center of measured travel)
 *
 *   2. Joystick:
 *        - center: ENA off, no STEP
 *        - hold deflection steady: STEP ramps from 0 up to (deflection * MAX)
 *          over ~0.5 s — this is the acceleration profile working
 *        - flip direction: brief decel, reverse, accel
 *        - hit a limit while pushing into it: position snaps, latch engages,
 *          motor stops; pushing the OTHER way clears the latch
 *
 *   3. Fire button: SOL LED pulses then cooldown.
 *
 *   4. Serial commands:
 *        h   re-run calibration
 *        p   pretend HOMED at 0 (skip calibration)
 *        s   stop axis
 *        c   clear FAULT
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "StepperAxis.h"
#include "JoystickAxis.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Hardware objects — every parameter pulled from constants.h / pins.h
// -----------------------------------------------------------------------------
StepperAxis goalkeeper(GK_STEP_PIN, GK_DIR_PIN, GK_LIMIT_HOME_PIN,
                       GK_STEPS_PER_MM, GK_AXIS_LENGTH_MM,
                       GK_MAX_SPEED, GK_ACCELERATION,
                       GK_ENA_PIN,
                       GK_LIMIT_FAR_PIN);

JoystickAxis joystick(JOY_PIN, goalkeeper,
                      JOY_DEADBAND, JOY_MAX_SPEED, JOY_UPDATE_MS);

Solenoid     kicker;   // pins + timings all from constants.h / pins.h

// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    Serial.println(F("\n=== FULL BENCH TEST ==="));
    Serial.println(F("Pins:  STEP=D2  DIR=D3  ENA=D4  SOL=D9"));
    Serial.println(F("       HOME=A1 FAR=A2  FIRE=D5 JOY=A0"));
    Serial.println();
    Serial.print(F("Joy max speed:    ")); Serial.print(JOY_MAX_SPEED, 0);          Serial.println(F(" steps/s"));
    Serial.print(F("Joy acceleration: ")); Serial.print(GK_JOY_ACCELERATION, 0);    Serial.println(F(" steps/s^2"));
    Serial.print(F("Cal hunt speed:   ")); Serial.print(GK_CAL_HUNT_SPEED, 0);      Serial.println(F(" steps/s"));
    Serial.print(F("Cal move speed:   ")); Serial.print(GK_CAL_MOVE_SPEED, 0);      Serial.println(F(" steps/s"));
    Serial.println();
    Serial.println(F("Commands: h=re-cal  p=pretend-homed  s=stop  c=clear-fault"));
    Serial.println();

    goalkeeper.init();
    kicker.begin();
    goalkeeper.home();   // kicks off the full calibration sequence
}

// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();
    kicker.update();

    if (goalkeeper.isHomed()) {
        joystick.update();
    }

    // ---- Serial commands ------------------------------------------------
    if (Serial.available()) {
        char c = Serial.read();
        switch (c) {
            case 'h': Serial.println(F("[CMD] re-calibrating")); goalkeeper.home();             break;
            case 'p': Serial.println(F("[CMD] pretend HOMED"));  goalkeeper.setHomedPretend();  break;
            case 's': Serial.println(F("[CMD] stop"));           goalkeeper.stop();             break;
            case 'c': goalkeeper.clearFault();                                                  break;
        }
    }

    // ---- State-transition logging --------------------------------------
    static AxisState lastAxisState = AxisState::UNINIT;
    AxisState curAxis = goalkeeper.getState();
    if (curAxis != lastAxisState) {
        Serial.print(F("[AXIS] -> "));
        Serial.println(goalkeeper.stateStr());
        lastAxisState = curAxis;
    }

    static SolenoidState lastSolState = SolenoidState::IDLE;
    SolenoidState curSol = kicker.getState();
    if (curSol != lastSolState) {
        Serial.print(F("[SOL ] -> "));
        switch (curSol) {
            case SolenoidState::IDLE:     Serial.println(F("IDLE"));     break;
            case SolenoidState::FIRING:   Serial.println(F("FIRING"));   break;
            case SolenoidState::COOLDOWN: Serial.println(F("COOLDOWN")); break;
        }
        lastSolState = curSol;
    }

    // ---- Periodic status ------------------------------------------------
    static unsigned long lastPrint = 0;
    unsigned long now = millis();
    if (now - lastPrint >= 500) {
        lastPrint = now;
        Serial.print(F("axis="));   Serial.print(goalkeeper.stateStr());
        Serial.print(F(" pos="));   Serial.print(goalkeeper.getPositionMm(), 1);
        Serial.print(F("/"));       Serial.print(goalkeeper.getMeasuredLengthMm(), 0);
        Serial.print(F(" defl="));  Serial.print(joystick.getDeflection(), 2);
        Serial.print(F(" ena="));   Serial.print(goalkeeper.isEnabled() ? F("ON ") : F("off"));
        Serial.print(F(" HOME="));  Serial.print(goalkeeper.homeLimitTriggered() ? F("PR") : F(".."));
        if (goalkeeper.isHomeLatched()) Serial.print(F("L"));
        Serial.print(F(" FAR="));   Serial.print(goalkeeper.farLimitTriggered() ? F("PR") : F(".."));
        if (goalkeeper.isFarLatched())  Serial.print(F("L"));
        Serial.print(F(" kick="));
        switch (kicker.getState()) {
            case SolenoidState::IDLE:     Serial.print(F("rdy"));  break;
            case SolenoidState::FIRING:   Serial.print(F("FIRE")); break;
            case SolenoidState::COOLDOWN: Serial.print(F("cool")); break;
        }
        Serial.println();
    }
}