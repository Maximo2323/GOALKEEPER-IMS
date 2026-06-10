/**
 * @file full-test.cpp
 * @brief Combined MANUAL + VISION test, switched live with the MODE button.
 *
 * One press of the MODE button (D5) toggles between the two modes:
 *
 *   MANUAL  — the joystick drives the goalkeeper axis, the fire button kicks
 *             the solenoid, and the limit switches enforce end-of-travel.
 *             (Same behaviour as manual-mode-test.cpp.)
 *
 *   VISION  — position and fire come from the visao UART stream over USB
 *             serial, exactly like vision-test.cpp:
 *               0x00..0xFD = ball X position (0..253) -> mapped to axis travel
 *               0xFE       = reserved (no-op)
 *               0xFF       = FIRE the solenoid
 *             Pair this mode with visao/vision-tracker.py.
 *
 * Pin layout (include/pins.h):
 *   D2  FAR limit   D3  HOME limit   D4  FIRE button   D5  MODE button
 *   D6  DIR   D7  STEP   D8  ENA   D9  SOL   A0  JOY
 *
 * Boot sequence:
 *   1. Full calibration runs first (home -> far -> center -> HOMED).
 *   2. Starts in MANUAL. Press MODE to switch to VISION and back.
 *
 * Serial:
 *   - Prints "CAL_MM:<len>" once after calibration (visao python waits for it).
 *   - Prints an "axis=... mode=..." heartbeat every 500 ms.
 *   - No text serial commands — in VISION mode every incoming byte is treated
 *     as position/fire, so a stray letter would collide. Mode is the BUTTON.
 *
 * To flash: copy over src/main.cpp (or drop in src/), then `pio run -t upload`.
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "StepperAxis.h"
#include "JoystickAxis.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Wire protocol — must match visao/vision-tracker.py + vision-test.cpp
// -----------------------------------------------------------------------------
static constexpr uint8_t  POS_BYTE_MAX     = 253;     // host clamps pos to 0..253
static constexpr uint8_t  BYTE_RSVD        = 0xFE;
static constexpr uint8_t  BYTE_FIRE        = 0xFF;
static constexpr float    POS_DEADBAND_MM  = 1.5f;    // ignore tiny re-targets
static constexpr unsigned long STATUS_PERIOD_MS = 500;

// Mode-button debounce window.
static constexpr unsigned long MODE_DEBOUNCE_MS = 30;

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

Solenoid     kicker;   // services the fire button (D4) inside kicker.update()

// -----------------------------------------------------------------------------
// Mode state
// -----------------------------------------------------------------------------
enum class Mode : uint8_t { MANUAL, VISION };
static Mode  mode                 = Mode::MANUAL;
static bool  calibrationAnnounced = false;
static float lastTargetMm         = -9999.0f;

static const char* modeStr(Mode m) { return m == Mode::MANUAL ? "MANUAL" : "VISION"; }

static void switchMode(Mode m) {
    if (m == mode) return;
    mode = m;
    goalkeeper.stop();            // clean handoff: stop whatever was moving
    lastTargetMm = -9999.0f;      // force the next vision target to apply
    if (mode == Mode::VISION) {
        while (Serial.available()) Serial.read();   // drop stale buffered bytes
    }
    Serial.print(F("[MODE] -> "));
    Serial.println(modeStr(mode));
}

// -----------------------------------------------------------------------------
// MODE button — toggle on a debounced rising edge (pull-down: pressed = HIGH)
// -----------------------------------------------------------------------------
static void pollModeButton() {
    const unsigned long now = millis();
    const bool pressed = (digitalRead(BTN_MODE_PIN) == MODE_PRESSED_LEVEL);

    static bool          lastReading = false;
    static bool          stable      = false;
    static unsigned long tEdge       = 0;

    if (pressed != lastReading) { tEdge = now; lastReading = pressed; }

    if (now - tEdge >= MODE_DEBOUNCE_MS && stable != lastReading) {
        stable = lastReading;
        if (stable) {             // rising edge = one fresh press
            switchMode(mode == Mode::MANUAL ? Mode::VISION : Mode::MANUAL);
        }
    }
}

// -----------------------------------------------------------------------------
// VISION — map an incoming position byte to an absolute move
// -----------------------------------------------------------------------------
static void handlePositionByte(uint8_t b) {
    if (!goalkeeper.isHomed()) return;
    const float L = goalkeeper.getMeasuredLengthMm();
    if (L <= 0.0f) return;

    // Invert left/right: byte 0 -> FAR end, byte 253 -> HOME end.
    // (Remove "POS_BYTE_MAX -" to go back to non-inverted mapping.)
    const float targetMm = ((float)(POS_BYTE_MAX - b) / (float)POS_BYTE_MAX) * L;
    if (fabs(targetMm - lastTargetMm) < POS_DEADBAND_MM) return;
    lastTargetMm = targetMm;
    goalkeeper.moveTo(targetMm);
}

static void handleVisionSerial() {
    while (Serial.available() > 0) {
        const int v = Serial.read();
        if (v < 0) return;
        const uint8_t b = (uint8_t)v;

        if      (b == BYTE_FIRE) kicker.fire();    // lib enforces cooldown
        else if (b == BYTE_RSVD) { /* reserved, no-op */ }
        else                     handlePositionByte(b);
    }
}

// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    pinMode(BTN_MODE_PIN, INPUT);   // external pull-down (pressed = HIGH)

    Serial.println(F("\n=== FULL TEST (MANUAL <-> VISION) ==="));
    Serial.println(F("Press the MODE button (D5) to toggle modes."));
    Serial.println(F("Calibrating..."));

    goalkeeper.init();
    kicker.begin();
    goalkeeper.home();              // kicks off full calibration
}

// -----------------------------------------------------------------------------
void loop() {
    goalkeeper.update();
    kicker.update();                // also services the fire button (D4)
    pollModeButton();

    // ---- active-mode behaviour ----------------------------------------------
    if (mode == Mode::MANUAL) {
        if (goalkeeper.isHomed()) joystick.update();
    } else {                        // VISION
        handleVisionSerial();
    }

    // ---- announce calibration once (visao python waits for this) ------------
    if (!calibrationAnnounced && goalkeeper.isCalibrated()) {
        Serial.print(F("CAL_MM:"));
        Serial.println(goalkeeper.getMeasuredLengthMm(), 1);
        calibrationAnnounced = true;
    }

    // ---- axis state-change log ----------------------------------------------
    static AxisState lastAxis = AxisState::UNINIT;
    if (goalkeeper.getState() != lastAxis) {
        Serial.print(F("[AXIS] -> "));
        Serial.println(goalkeeper.stateStr());
        lastAxis = goalkeeper.getState();
    }

    // ---- periodic heartbeat (line starts with "axis=" for the python) -------
    static unsigned long lastPrint = 0;
    const unsigned long now = millis();
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
        Serial.print(F(" mode=")); Serial.print(modeStr(mode));
        Serial.println();
    }
}
