/**
 * @file manual-mode-test.cpp
 * @brief Scripted bench test: run the stepper through a motion sequence,
 *        fire the solenoid once at the end, then drop into interactive mode
 *        with joystick + fire button while continuously logging every input.
 *
 * Pin layout (see include/pins.h):
 *   D2  LIMIT_FAR    far  limit switch
 *   D3  LIMIT_HOME   home limit switch
 *   D4  BTN_MODE     mode toggle   -> reported only (no behaviour yet)
 *   D5  BTN_FIRE     fire button   -> kicks solenoid
 *   D6  DIR          stepper driver direction
 *   D7  STEP         stepper driver step pulse
 *   D8  ENA          stepper driver enable (active-LOW)
 *   D9  SOL_MOSFET   solenoid gate (active-HIGH)
 *   A0  JOY          joystick X (analog)
 *
 * Test flow:
 *   1. Boot -> StepperAxis::home() runs full calibration
 *      (HOMING_HOME -> HOMING_FAR -> MOVE_TO_CENTER -> HOMED)
 *   2. Once calibrated, scripted sequence:
 *        a. move to 85% of measured length
 *        b. move to 15% of measured length
 *        c. move to 50% (center)
 *        d. wait ~500 ms, fire solenoid once
 *   3. IDLE phase — joystick controls the axis, fire button kicks again.
 *
 * Throughout, every ~200 ms a line of input states is printed:
 *   FIRE=.. MODE=.. HOME=.. FAR=.. JOY=512 (defl=+0.00) axis=HOMED pos=250
 *
 * To flash this test:
 *   - copy this file's contents over src/main.cpp, OR
 *   - rename src/main.cpp to .bak and drop this in src/, then `pio run -t upload`.
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "StepperAxis.h"
#include "JoystickAxis.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Hardware
// -----------------------------------------------------------------------------
StepperAxis goalkeeper(GK_STEP_PIN, GK_DIR_PIN, GK_LIMIT_HOME_PIN,
                       GK_STEPS_PER_MM, GK_AXIS_LENGTH_MM,
                       GK_MAX_SPEED, GK_ACCELERATION,
                       GK_ENA_PIN,
                       GK_LIMIT_FAR_PIN);

JoystickAxis joystick(JOY_PIN, goalkeeper,
                      JOY_DEADBAND, JOY_MAX_SPEED, JOY_UPDATE_MS);

Solenoid     kicker;   // defaults to SOL_MOSFET_PIN (D9) + SOL_BUTTON_PIN (D5)

// -----------------------------------------------------------------------------
// Bench sequence state machine
// -----------------------------------------------------------------------------
enum class BenchPhase : uint8_t {
    CALIBRATING,
    MOVE_TO_FAR,
    MOVE_TO_HOME,
    MOVE_TO_CENTER,
    SETTLE_BEFORE_KICK,
    IDLE
};

static BenchPhase     phase            = BenchPhase::CALIBRATING;
static unsigned long  phaseEnteredMs   = 0;
static constexpr unsigned long SETTLE_MS = 500;
static constexpr unsigned long REPORT_PERIOD_MS = 200;

static const char* phaseStr(BenchPhase p) {
    switch (p) {
        case BenchPhase::CALIBRATING:        return "CAL";
        case BenchPhase::MOVE_TO_FAR:        return "FAR";
        case BenchPhase::MOVE_TO_HOME:       return "HOME";
        case BenchPhase::MOVE_TO_CENTER:     return "CENTER";
        case BenchPhase::SETTLE_BEFORE_KICK: return "SETTLE";
        case BenchPhase::IDLE:               return "IDLE";
    }
    return "?";
}

static void enterPhase(BenchPhase p) {
    phase          = p;
    phaseEnteredMs = millis();
    Serial.print(F("[BENCH] -> "));
    Serial.println(phaseStr(p));
}

// -----------------------------------------------------------------------------
// Input readers (raw — independent of the StepperAxis internals so we can
// confirm wiring directly on the serial monitor).
// -----------------------------------------------------------------------------
static bool readFireBtn() { return digitalRead(BTN_FIRE_PIN) == SOL_BUTTON_PRESSED; }
static bool readModeBtn() { return digitalRead(BTN_MODE_PIN) == MODE_PRESSED_LEVEL; }
static bool readHomeLim() { return digitalRead(GK_LIMIT_HOME_PIN) == LIMIT_TRIGGERED; }
static bool readFarLim()  { return digitalRead(GK_LIMIT_FAR_PIN)  == LIMIT_TRIGGERED; }

// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    // Mode button isn't owned by any library — set it up here.
    pinMode(BTN_MODE_PIN, INPUT);

    Serial.println(F("\n=== MANUAL MODE TEST ==="));
    Serial.println(F("Pins  FAR=D2 HOME=D3 MODE=D4 FIRE=D5"));
    Serial.println(F("      DIR=D6 STEP=D7 ENA=D8 SOL=D9 JOY=A0"));
    Serial.println();
    Serial.println(F("Sequence: calibrate -> 85% -> 15% -> 50% -> KICK -> idle (joystick)"));
    Serial.println();

    goalkeeper.init();
    kicker.begin();
    goalkeeper.home();
    enterPhase(BenchPhase::CALIBRATING);
}

// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();
    kicker.update();

    // Joystick is only allowed to drive the axis once the scripted sequence
    // has finished — otherwise it would fight the bench moves.
    if (phase == BenchPhase::IDLE) {
        joystick.update();
    }

    // -------------------------------------------------------------------------
    // Bench sequence
    // -------------------------------------------------------------------------
    const unsigned long now = millis();

    switch (phase) {
        case BenchPhase::CALIBRATING:
            if (goalkeeper.isCalibrated() &&
                goalkeeper.getState() == AxisState::HOMED) {
                const float L = goalkeeper.getMeasuredLengthMm();
                goalkeeper.moveTo(L * 0.85f);
                enterPhase(BenchPhase::MOVE_TO_FAR);
            }
            break;

        case BenchPhase::MOVE_TO_FAR:
            if (goalkeeper.getState() == AxisState::HOMED) {
                goalkeeper.moveTo(goalkeeper.getMeasuredLengthMm() * 0.15f);
                enterPhase(BenchPhase::MOVE_TO_HOME);
            }
            break;

        case BenchPhase::MOVE_TO_HOME:
            if (goalkeeper.getState() == AxisState::HOMED) {
                goalkeeper.moveTo(goalkeeper.getMeasuredLengthMm() * 0.50f);
                enterPhase(BenchPhase::MOVE_TO_CENTER);
            }
            break;

        case BenchPhase::MOVE_TO_CENTER:
            if (goalkeeper.getState() == AxisState::HOMED) {
                enterPhase(BenchPhase::SETTLE_BEFORE_KICK);
            }
            break;

        case BenchPhase::SETTLE_BEFORE_KICK:
            if (now - phaseEnteredMs >= SETTLE_MS) {
                if (kicker.fire()) Serial.println(F("[BENCH] solenoid fired"));
                else               Serial.println(F("[BENCH] kicker rejected fire (cooldown)"));
                enterPhase(BenchPhase::IDLE);
                Serial.println(F("[BENCH] joystick + fire button now active"));
            }
            break;

        case BenchPhase::IDLE:
            break;
    }

    // -------------------------------------------------------------------------
    // Periodic input report
    // -------------------------------------------------------------------------
    static unsigned long lastReportMs = 0;
    if (now - lastReportMs >= REPORT_PERIOD_MS) {
        lastReportMs = now;

        const int joyRaw = analogRead(JOY_PIN);
        const float defl = joystick.getDeflection();

        Serial.print(F("phase=")); Serial.print(phaseStr(phase));
        Serial.print(F(" axis=")); Serial.print(goalkeeper.stateStr());
        Serial.print(F(" pos="));  Serial.print(goalkeeper.getPositionMm(), 0);
        Serial.print(F("/"));      Serial.print(goalkeeper.getMeasuredLengthMm(), 0);

        Serial.print(F(" FIRE=")); Serial.print(readFireBtn() ? F("PR") : F(".."));
        Serial.print(F(" MODE=")); Serial.print(readModeBtn() ? F("PR") : F(".."));

        Serial.print(F(" HOME=")); Serial.print(readHomeLim() ? F("PR") : F(".."));
        Serial.print(F(" FAR="));  Serial.print(readFarLim()  ? F("PR") : F(".."));

        Serial.print(F(" JOY="));  Serial.print(joyRaw);
        Serial.print(F(" ("));     Serial.print(defl, 2); Serial.print(F(")"));

        Serial.print(F(" kick="));
        switch (kicker.getState()) {
            case SolenoidState::IDLE:     Serial.print(F("rdy"));  break;
            case SolenoidState::FIRING:   Serial.print(F("FIRE")); break;
            case SolenoidState::COOLDOWN: Serial.print(F("cool")); break;
        }
        Serial.println();
    }
}
