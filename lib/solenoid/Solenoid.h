#pragma once

#include <Arduino.h>
#include "constants.h"
#include "pins.h"

// =============================================================================
// Solenoid — non-blocking kicker driver with optional fire button
// =============================================================================
// Drives a low-side N-MOSFET that switches a solenoid coil. Includes:
//   - timed pulse: gate goes HIGH for SOL_PULSE_MS, then LOW
//   - cooldown:    further fire requests rejected for SOL_COOLDOWN_MS after
//                  the pulse ends (so the bulk capacitor can recharge)
//   - safety cap:  hard force-off if ON longer than SOL_MAX_ON_MS for any reason
//   - bundled fire button: a single press fires once (edge detect, no
//     auto-repeat while held)
//
// State machine:
//
//        +---------+   fire()   +---------+   t >= PULSE   +-----------+
//        |  IDLE   |----------->| FIRING  |--------------->| COOLDOWN  |
//        +---------+   (cap ok) +---------+                +-----------+
//             ^                                                  |
//             +--- t >= PULSE + COOLDOWN ------------------------+
//
// Usage:
//   Solenoid kicker;
//   void setup() { kicker.begin(); }
//   void loop()  { kicker.update(); }      // handles pulse timing + button
//
//   // Fire from code (auto mode, Pi command, etc.):
//   if (kicker.canFire()) kicker.fire();
// =============================================================================

enum class SolenoidState : uint8_t {
    IDLE,       // ready to fire
    FIRING,     // gate HIGH, coil energized
    COOLDOWN    // gate LOW but locked out until cap recharges
};

class Solenoid {
public:
    // mosfetPin defaults to SOL_MOSFET_PIN; buttonPin defaults to SOL_BUTTON_PIN.
    // Pass 255 for buttonPin if no fire button is wired.
    explicit Solenoid(uint8_t mosfetPin = SOL_MOSFET_PIN,
                      uint8_t buttonPin = SOL_BUTTON_PIN);

    void begin();
    void update();

    // Request a kick. Returns true if the pulse started, false if rejected
    // (still in FIRING or COOLDOWN). Silent rejection — caller can check
    // canFire() first if they care.
    bool fire();

    bool canFire()    const { return _state == SolenoidState::IDLE; }
    bool isFiring()   const { return _state == SolenoidState::FIRING; }
    bool inCooldown() const { return _state == SolenoidState::COOLDOWN; }
    SolenoidState getState() const { return _state; }

    // Force everything off and reset to IDLE. Use for emergency stop or
    // when entering AUTO mode and you want a clean slate.
    void reset();

    // Time (ms) until canFire() becomes true. 0 if already idle.
    unsigned long timeUntilReady() const;

private:
    uint8_t _mosfetPin;
    uint8_t _buttonPin;     // 255 = no button

    SolenoidState _state;
    unsigned long _pulseStartMs;
    unsigned long _cooldownStartMs;

    // Button edge detect — same approach as your LimitSwitch class
    bool _btnPressed;
    bool _btnLastPressed;

    void _setOutput(uint8_t level);
    void _readButton();
};