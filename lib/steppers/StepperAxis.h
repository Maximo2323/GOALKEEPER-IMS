#pragma once

#include <AccelStepper.h>
#include "constants.h"

// =============================================================================
// StepperAxis — limit-switch-authoritative positioning
// =============================================================================
// Position rules:
//   - The limit switches are the SINGLE SOURCE OF TRUTH. The "digital" position
//     is just bookkeeping; if it disagrees with a switch, the switch wins.
//   - On boot, calibrate() runs:
//       1. Move toward HOME at homing speed   -> set pos = 0 when HOME hits
//       2. Move toward FAR  at homing speed   -> record _measuredLengthMm when FAR hits
//       3. Move to the center of measured travel
//       4. -> HOMED
//   - During runtime moves:
//       - moveTo() does NOT clamp to digital limits. Joystick / commands can
//         freely command targets beyond _measuredLengthMm or below 0; the
//         stepper will just keep stepping until a limit switch hits.
//       - When HOME limit is hit while moving toward home: pos := 0,
//         motor stops, HOME is "latched" (further moves toward home refused
//         until joystick/command moves the other way).
//       - When FAR limit is hit while moving toward far: pos := _measuredLengthMm,
//         motor stops, FAR is "latched".
//       - Limits hit while moving away from them are ignored (impossible
//         mechanically, but cheap to guard).
//
// State machine:
//   UNINIT
//      v  home()
//   HOMING_TO_HOME    -- toward home limit at GK_CAL_HUNT_SPEED
//      v  HOME hit -> pos = 0
//   BACKOFF_FROM_HOME -- back off GK_BACKOFF_MM (snappy, high accel)
//      v
//   HOMING_TO_FAR     -- toward far limit at GK_CAL_HUNT_SPEED
//      v  FAR hit -> _measuredLengthMm = pos
//   MOVE_TO_CENTER    -- one continuous move from FAR straight to center
//                        (no separate backoff phase — the move *is* the backoff)
//      v  arrived
//   HOMED             -- ready
//   HOMED             -- ready
//      v  moveTo() / joystick
//   RUNNING -> HOMED on arrival OR limit hit
//
// FAULT is now reserved for hard errors only (limit hit while moving away
// from it = wiring problem). Normal limit contact during motion is NOT a fault.
// =============================================================================

enum class AxisState {
    UNINIT,
    HOMING_TO_HOME,
    BACKOFF_FROM_HOME,
    HOMING_TO_FAR,
    MOVE_TO_CENTER,    // also handles the implicit backoff from FAR
    HOMED,
    RUNNING,           // accelerated move to a position target (vision moveTo)
    VELOCITY,          // constant-speed move (joystick); NO acceleration ramp
    STOPPING,          // decelerating to a controlled stop (accel path only)
    FAULT
};

class StepperAxis {
public:
    StepperAxis(uint8_t stepPin, uint8_t dirPin,
                uint8_t homeLimitPin,
                float stepsPerMm, float axisLengthMm,
                float maxSpeed, float acceleration,
                uint8_t enaPin      = 255,
                uint8_t farLimitPin = 255);

    void init();
    void update();

    // Start the full calibration sequence (home -> far -> center -> HOMED).
    // FAR limit pin is required; if not wired, only homes to HOME and stops there.
    void home();

    // Command an absolute position in mm. NOT clamped — limit switches handle
    // the actual end-of-travel. Refused only if the corresponding limit is
    // currently latched against this direction of motion.
    void moveTo(float mm);

    void moveBy(float mm);

    // Direct velocity control — NO acceleration ramp. Sign sets direction:
    //   +steps/sec drives toward FAR, -steps/sec toward HOME, |v| < 1 stops.
    // Used by the joystick for speed-proportional manual control: the further
    // the stick is pushed, the larger the magnitude passed here.
    void setVelocity(float stepsPerSec);

    void stop();
    void emergencyStop();

    void enable();
    void disable();
    bool isEnabled() const { return _enabled; }

    void setMaxSpeedRuntime(float stepsPerSec);
    void adoptPositionMm(float mm);

    // BENCH ONLY — skip calibration, declare HOMED at 0.
    void setHomedPretend();

    // Clear FAULT and return to UNINIT (caller should re-home).
    void clearFault();

    // Status queries
    AxisState   getState()         const { return _state; }
    float       getPositionMm();
    float       getTargetMm();

    // The travel length we actually measured during calibration. Returns the
    // initial estimate (GK_AXIS_LENGTH_MM) until calibration completes.
    float       getMeasuredLengthMm() const { return _measuredLengthMm; }

    // Legacy accessor — returns the measured length once calibrated, otherwise
    // the initial estimate. Most callers should use getMeasuredLengthMm().
    float       getAxisLengthMm()  const { return _measuredLengthMm; }

    bool        isMoving();
    bool        isHomed()          const { return _state == AxisState::HOMED ||
                                                  _state == AxisState::RUNNING ||
                                                  _state == AxisState::VELOCITY ||
                                                  _state == AxisState::STOPPING; }
    bool        isCalibrated()     const { return _calibrated; }

    bool        homeLimitTriggered();
    bool        farLimitTriggered();

    // True when the corresponding limit has been hit and motion in that
    // direction is currently locked out. Cleared automatically when a move
    // in the opposite direction is commanded.
    bool        isHomeLatched()    const { return _homeLatched; }
    bool        isFarLatched()     const { return _farLatched; }

    const char* stateStr()         const;

private:
    AccelStepper _stepper;

    uint8_t _homeLimitPin;
    uint8_t _farLimitPin;       // 255 if not wired
    uint8_t _enaPin;
    bool    _enabled;

    float   _stepsPerMm;
    float   _axisLengthMm;       // initial estimate (from constants)
    float   _measuredLengthMm;   // measured at calibration; == estimate until then
    bool    _calibrated;

    float   _maxSpeed;
    float   _acceleration;
    float   _homingSpeed;
    long    _backoffSteps;

    bool    _homeLatched;        // can't move toward home until cleared
    bool    _farLatched;

    // Coordinate offset: physical_position_steps = _stepper.currentPosition() - _zeroOffsetSteps.
    // This lets us "redefine where 0 is" (e.g. when the HOME limit is found
    // mid-motion) WITHOUT calling _stepper.setCurrentPosition(), which has
    // the side effect of zeroing AccelStepper's internal velocity and
    // breaking the acceleration profile.
    long    _zeroOffsetSteps;

    // Commanded velocity (signed steps/sec) while in AxisState::VELOCITY.
    float   _velStepsPerSec;

    AxisState _state;

    long  mmToSteps(float mm)   { return (long)(mm * _stepsPerMm); }
    float stepsToMm(long steps) { return (float)steps / _stepsPerMm; }

    bool  _readPin(uint8_t pin) const;
    void  _setState(AxisState s);
    void  _endVelocity();   // zero velocity; return to HOMED if in VELOCITY

    // Begin a homing-speed move toward home (negative direction).
    void  _startHomingToward(int8_t direction);
};