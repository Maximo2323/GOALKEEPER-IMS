/**
 * @file solenoid-uart-pc.cpp
 * @brief Standalone test for the solenoid kicker driven by a low-side N-MOSFET.
 *
 * =============================================================================
 *                              HARDWARE WIRING
 * =============================================================================
 *
 *   Solenoid power circuit (low-side N-MOSFET, e.g. IRLZ44N / IRL540N):
 *
 *      +V (12-24V solenoid supply, big bulk cap across +V/GND)
 *       |
 *      [SOLENOID COIL]
 *       |
 *       +---|>|---+        (flyback diode across coil, cathode to +V,
 *       |  diode  |         anode to drain. 1N5408 / SB560 / similar.)
 *       |         |
 *       +---------+
 *       |
 *      DRAIN
 *       |
 *      [N-MOSFET]   GATE  <-- D9 (SOL_MOSFET_PIN), through ~150R series resistor
 *       |           GATE  <-- 10k pulldown to GND (so coil stays off at boot)
 *      SOURCE
 *       |
 *      GND  (common ground with Arduino!)
 *
 *   Fire button (optional):
 *      D2 (SOL_BUTTON_PIN / BTN_FIRE_PIN) -> pull-down resistor to GND,
 *      other side of button -> VCC. INPUT mode. Pressed reads HIGH.
 *      (Wiring: GND -> resistor -> pin -> button -> VCC. See constants.h.)
 *
 * =============================================================================
 *                       THE THREE TIMING CONSTANTS
 * =============================================================================
 *
 *   All three live in include/constants.h under "SOLENOID KICKER".
 *
 *   SOL_PULSE_MS       (currently 50 ms)
 *     -> How long the gate is held HIGH = how long the coil is energized
 *        = how long the plunger is OUT (the actual "kick" duration).
 *        Bigger = harder/longer push but more heat in the coil.
 *        Most kicker solenoids want 20-80 ms. If your kick feels weak,
 *        try 80-120 ms. If the coil gets hot fast, lower it.
 *
 *   SOL_COOLDOWN_MS    (currently 800 ms)
 *     -> Lock-out period AFTER the pulse ends. fire() is rejected during
 *        this window. Two reasons:
 *          (a) gives your bulk capacitor time to recharge so the next
 *              shot is just as strong (cap droop = weak second kick)
 *          (b) prevents the coil from being re-energized while still warm
 *        Bigger = safer, slower rate of fire. Smaller = faster repeat but
 *        risk of weaker shots and heat buildup.
 *
 *   SOL_MAX_ON_MS      (currently 250 ms, MUST be > SOL_PULSE_MS)
 *     -> Hard safety ceiling. If for ANY reason the gate has been HIGH
 *        longer than this (bug, stuck state, missed timer), the driver
 *        forces it LOW. This is your fuse-of-last-resort against burning
 *        out the coil. You should never actually hit this in normal use.
 *
 * =============================================================================
 *                           SERIAL COMMANDS
 * =============================================================================
 *
 *   f   fire once now (rejected if still in cooldown)
 *   a   toggle AUTO mode (fires every SOL_PULSE_MS + SOL_COOLDOWN_MS)
 *   s   print current state + timing constants
 *   r   reset (force coil off, clear cooldown)
 *
 *   Or just press the physical fire button on SOL_BUTTON_PIN.
 *
 * =============================================================================
 *                       EXPECTED LED / COIL BEHAVIOR
 * =============================================================================
 *
 *   Press fire button (or send 'f'):
 *     - Coil clicks ON for SOL_PULSE_MS (50 ms by default — quick "thunk")
 *     - Serial shows: FIRING -> COOLDOWN -> IDLE
 *     - For ~SOL_COOLDOWN_MS after, fire() is rejected silently
 *
 *   Send 'a' for auto mode:
 *     - You'll see a kick roughly every 850 ms (50 ms pulse + 800 ms cooldown)
 *     - Send 'a' again to stop
 *
 *   For bench testing without the actual solenoid: just put an LED + 330R
 *   resistor between D9 and GND (D9 -> LED anode -> 330R -> GND).
 *   The LED will blink for SOL_PULSE_MS each fire.
 * =============================================================================
 */

#include <Arduino.h>
#include "constants.h"
#include "pins.h"
#include "Solenoid.h"

// -----------------------------------------------------------------------------
// Hardware object
// -----------------------------------------------------------------------------
Solenoid kicker;   // defaults to SOL_MOSFET_PIN (D9) and SOL_BUTTON_PIN (D5)

// AUTO mode: fire on a fixed period equal to the full cycle time.
static bool          autoMode      = false;
static unsigned long lastAutoFire  = 0;
static const unsigned long AUTO_PERIOD_MS = SOL_PULSE_MS + SOL_COOLDOWN_MS + 50;

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------
static const __FlashStringHelper* stateStr(SolenoidState s) {
    switch (s) {
        case SolenoidState::IDLE:     return F("IDLE");
        case SolenoidState::FIRING:   return F("FIRING");
        case SolenoidState::COOLDOWN: return F("COOLDOWN");
    }
    return F("?");
}

static void printConfig() {
    Serial.println(F("--- Solenoid config ---"));
    Serial.print  (F("  SOL_MOSFET_PIN     = D")); Serial.println(SOL_MOSFET_PIN);
    Serial.print  (F("  SOL_BUTTON_PIN     = D")); Serial.println(SOL_BUTTON_PIN);
    Serial.print  (F("  SOL_FIRE_LEVEL     = ")); Serial.println(SOL_FIRE_LEVEL == HIGH ? F("HIGH") : F("LOW"));
    Serial.print  (F("  SOL_PULSE_MS       = ")); Serial.println(SOL_PULSE_MS);
    Serial.print  (F("  SOL_COOLDOWN_MS    = ")); Serial.println(SOL_COOLDOWN_MS);
    Serial.print  (F("  SOL_MAX_ON_MS      = ")); Serial.println(SOL_MAX_ON_MS);
    Serial.print  (F("  Auto-mode period   = ")); Serial.print(AUTO_PERIOD_MS); Serial.println(F(" ms"));
    Serial.println();
}

// -----------------------------------------------------------------------------
// Setup
// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial && millis() < 2000) {}

    Serial.println(F("\n=== SOLENOID TEST ==="));
    printConfig();

    kicker.begin();   // sets pinMode OUTPUT and writes SOL_OFF_LEVEL

    Serial.println(F("Commands:  f=fire   a=auto toggle   s=status   r=reset"));
    Serial.println();
}

// -----------------------------------------------------------------------------
// Loop
// -----------------------------------------------------------------------------
void loop() {
    // The library handles: button edge-detect, pulse timing, cooldown,
    // and the SOL_MAX_ON_MS safety cap. Call this every loop iteration.
    kicker.update();

    // ---- auto-fire mode -------------------------------------------------
    if (autoMode && kicker.canFire() && (millis() - lastAutoFire >= AUTO_PERIOD_MS)) {
        lastAutoFire = millis();
        kicker.fire();
    }

    // ---- serial commands ------------------------------------------------
    if (Serial.available()) {
        char c = Serial.read();
        switch (c) {
            case 'f':
                if (kicker.fire()) {
                    Serial.println(F("[CMD] fired"));
                } else {
                    Serial.print(F("[CMD] rejected — "));
                    Serial.print(kicker.timeUntilReady());
                    Serial.println(F(" ms until ready"));
                }
                break;
            case 'a':
                autoMode = !autoMode;
                lastAutoFire = 0;
                Serial.print(F("[CMD] auto mode "));
                Serial.println(autoMode ? F("ON") : F("OFF"));
                break;
            case 's':
                printConfig();
                break;
            case 'r':
                kicker.reset();
                Serial.println(F("[CMD] reset — coil OFF, state IDLE"));
                break;
            default: break;
        }
    }

    // ---- state-transition logging --------------------------------------
    static SolenoidState lastState = SolenoidState::IDLE;
    SolenoidState cur = kicker.getState();
    if (cur != lastState) {
        Serial.print(F("[STATE] -> "));
        Serial.println(stateStr(cur));
        lastState = cur;
    }
}
