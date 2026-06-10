/**
 * @file vision-test.cpp
 * @brief Arduino firmware for the vision-driven mode.
 *
 * Pairs with visao/vision-tracker.py. Wire protocol (single-byte stream, both ways):
 *
 *   HOST -> ARDUINO
 *     0x00..0xFD   = ball X position (0..253), mapped linearly across the
 *                    measured axis length. The stepper goes there.
 *     0xFE         = reserved (no-op for now).
 *     0xFF         = FIRE kick. kicker.fire() is invoked immediately
 *                    (Arduino still enforces its own pulse/cooldown).
 *
 *   ARDUINO -> HOST  (printable text, '\n'-terminated)
 *     "CAL_MM:<float>"        once, when calibration completes
 *     "[AXIS] -> <state>"     on every axis state change
 *     "axis=<state> pos=<mm>/<len> tgt=<mm> kick=<state>"
 *                             every STATUS_PERIOD_MS as a heartbeat
 *
 * Python reads these lines and won't send position bytes until it sees
 * CAL_MM, so the carriage will not move during the homing sequence.
 *
 * To upload this sketch instead of main.cpp:
 *   - copy this file's contents over src/main.cpp, OR
 *   - rename src/main.cpp to .bak and drop this in src/, then
 *     `pio run -t upload`.
 *
 * NOTE: No text serial commands ('h','p','s','c','f') in this build —
 * those bytes collide with position bytes from Python. Use the regular
 * main.cpp build for serial-monitor-driven debugging.
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "StepperAxis.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Wire protocol — must match visao_debug.py
// -----------------------------------------------------------------------------
static constexpr uint8_t POS_BYTE_MAX = 253;   // host clamps position to 0..253
static constexpr uint8_t BYTE_FIRE    = 0xFF;
static constexpr uint8_t BYTE_RSVD    = 0xFE;

// -----------------------------------------------------------------------------
// Timing
// -----------------------------------------------------------------------------
static constexpr unsigned long STATUS_PERIOD_MS = 500;
// Ignore tiny re-targets from the host (the same x_norm coming back as the
// ball jitters by 1 px would otherwise restart the accel profile).
static constexpr float POS_DEADBAND_MM = 1.5f;

// -----------------------------------------------------------------------------
// Hardware
// -----------------------------------------------------------------------------
StepperAxis goalkeeper(GK_STEP_PIN, GK_DIR_PIN, GK_LIMIT_HOME_PIN,
                       GK_STEPS_PER_MM, GK_AXIS_LENGTH_MM,
                       GK_MAX_SPEED, GK_ACCELERATION,
                       GK_ENA_PIN,
                       GK_LIMIT_FAR_PIN);

Solenoid kicker;

// -----------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------
static bool  calibrationAnnounced = false;
static float lastTargetMm         = -9999.0f;

// -----------------------------------------------------------------------------
static void announceCalibration() {
    Serial.print(F("CAL_MM:"));
    Serial.println(goalkeeper.getMeasuredLengthMm(), 1);
    calibrationAnnounced = true;
}

static void handlePositionByte(uint8_t b) {
    if (!goalkeeper.isHomed()) return;   // ignore until safe to move

    const float L = goalkeeper.getMeasuredLengthMm();
    if (L <= 0.0f) return;

    // Invert left/right: byte 0 -> FAR end, byte 253 -> HOME end.
    // (Remove "POS_BYTE_MAX -" to go back to non-inverted mapping.)
    const float fraction = (float)(POS_BYTE_MAX - b) / (float)POS_BYTE_MAX;   // 0..1
    const float targetMm = fraction * L;

    if (fabs(targetMm - lastTargetMm) < POS_DEADBAND_MM) return;
    lastTargetMm = targetMm;
    goalkeeper.moveTo(targetMm);
}

static void handleSerialIn() {
    while (Serial.available() > 0) {
        const int v = Serial.read();
        if (v < 0) return;
        const uint8_t b = (uint8_t)v;

        if (b == BYTE_FIRE) {
            // Honor every fire request — the Solenoid lib enforces cooldown.
            if (kicker.fire()) Serial.println(F("[KICK] fired"));
            else               Serial.println(F("[KICK] rejected (cooldown)"));
        } else if (b == BYTE_RSVD) {
            // reserved, no-op
        } else {
            handlePositionByte(b);
        }
    }
}

// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    Serial.println(F("\n=== VISAO DEBUG FIRMWARE ==="));
    Serial.println(F("Protocol: 0..253=pos, 0xFF=fire"));
    Serial.println(F("Waiting for calibration..."));

    goalkeeper.init();
    kicker.begin();
    goalkeeper.home();
}

// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();
    kicker.update();

    handleSerialIn();

    // ---- announce calibration the first time we enter HOMED -----------
    if (!calibrationAnnounced && goalkeeper.isCalibrated()) {
        announceCalibration();
    }

    // ---- state-change logging -----------------------------------------
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

    // ---- periodic heartbeat (Python parses this line) -----------------
    static unsigned long lastPrint = 0;
    unsigned long now = millis();
    if (now - lastPrint >= STATUS_PERIOD_MS) {
        lastPrint = now;
        Serial.print(F("axis="));  Serial.print(goalkeeper.stateStr());
        Serial.print(F(" pos="));  Serial.print(goalkeeper.getPositionMm(), 1);
        Serial.print(F("/"));      Serial.print(goalkeeper.getMeasuredLengthMm(), 0);
        Serial.print(F(" tgt="));  Serial.print(goalkeeper.getTargetMm(), 1);
        Serial.print(F(" kick="));
        switch (kicker.getState()) {
            case SolenoidState::IDLE:     Serial.print(F("rdy"));  break;
            case SolenoidState::FIRING:   Serial.print(F("FIRE")); break;
            case SolenoidState::COOLDOWN: Serial.print(F("cool")); break;
        }
        Serial.println();
    }
}
