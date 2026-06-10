#include "StepperAxis.h"

// =============================================================================
// Coordinate convention
// =============================================================================
// AccelStepper tracks its own internal position, which we never reset after
// init(). Our public position is computed as:
//
//     position_steps = _stepper.currentPosition() - _zeroOffsetSteps
//
// "Re-zeroing" simply updates _zeroOffsetSteps; AccelStepper keeps its
// momentum, deceleration profile, and stepInterval state intact. This is
// the key to smooth limit-handoff: the motor decelerates naturally to the
// new target without any "stop and re-accelerate" lurch.
// =============================================================================

// A sentinel target far past either physical end of travel; the motor will
// never reach it because a limit will trip first.
static constexpr long HUNT_TARGET_STEPS = 1000000L;   // ~100 m at 10 steps/mm

StepperAxis::StepperAxis(uint8_t stepPin, uint8_t dirPin,
                         uint8_t homeLimitPin,
                         float stepsPerMm, float axisLengthMm,
                         float maxSpeed, float acceleration,
                         uint8_t enaPin,
                         uint8_t farLimitPin)
    : _stepper(AccelStepper::DRIVER, stepPin, dirPin),
      _homeLimitPin(homeLimitPin),
      _farLimitPin(farLimitPin),
      _enaPin(enaPin),
      _enabled(false),
      _stepsPerMm(stepsPerMm),
      _axisLengthMm(axisLengthMm),
      _measuredLengthMm(axisLengthMm),
      _calibrated(false),
      _maxSpeed(maxSpeed),
      _acceleration(acceleration),
      _homingSpeed(GK_CAL_HUNT_SPEED),
      _backoffSteps((long)(GK_BACKOFF_MM * stepsPerMm)),
      _homeLatched(false),
      _farLatched(false),
      _zeroOffsetSteps(0),
      _velStepsPerSec(0.0f),
      _state(AxisState::UNINIT)
{}

void StepperAxis::init() {
    pinMode(_homeLimitPin, INPUT_PULLUP);
    if (_farLimitPin != 255) pinMode(_farLimitPin, INPUT_PULLUP);

    if (_enaPin != 255) {
        pinMode(_enaPin, OUTPUT);
        digitalWrite(_enaPin, STEPPER_DISABLE);
        _enabled = false;
    } else {
        _enabled = true;
    }

    _stepper.setMaxSpeed(_maxSpeed);
    _stepper.setAcceleration(_acceleration);
    _stepper.setCurrentPosition(0);
    _zeroOffsetSteps = 0;
    _setState(AxisState::UNINIT);
}

// =============================================================================
// State machine — every transition keeps motor velocity continuous.
// =============================================================================
void StepperAxis::update() {
    switch (_state) {
        case AxisState::UNINIT:
        case AxisState::FAULT:
            break;

        // ---------- Phase 1: hunt for HOME (accelerated) ----------
        case AxisState::HOMING_TO_HOME:
            if (homeLimitTriggered()) {
                // Define current physical position as logical 0.
                _zeroOffsetSteps = _stepper.currentPosition();
                // Hard stop at the switch (don't decelerate through it).
                _stepper.setSpeed(0);

                if (_farLimitPin == 255) {
                    // No FAR limit wired -> calibration done here.
                    _stepper.moveTo(_stepper.currentPosition());
                    _measuredLengthMm = _axisLengthMm;
                    _calibrated = true;
                    _setState(AxisState::HOMED);
                    Serial.println(F("[AXIS] HOME found. No FAR limit — calibration done."));
                } else {
                    // Skip the explicit backoff. Issue ONE accelerated move
                    // straight toward FAR; the motor will accelerate from
                    // rest, cruise at hunt speed, and the FAR-search state
                    // takes over to detect that switch.
                    _stepper.setMaxSpeed(GK_CAL_HUNT_SPEED);
                    _stepper.setAcceleration(GK_CAL_HUNT_ACCELERATION);
                    _stepper.moveTo(_stepper.currentPosition() + HUNT_TARGET_STEPS);
                    _setState(AxisState::HOMING_TO_FAR);
                    Serial.println(F("[AXIS] HOME found. Position = 0. Searching for FAR..."));
                }
            } else {
                _stepper.run();
            }
            break;

        // BACKOFF_FROM_HOME is no longer entered, but kept for ABI compat.
        case AxisState::BACKOFF_FROM_HOME:
            _setState(AxisState::HOMED);
            break;

        // ---------- Phase 2: hunt for FAR (accelerated) ----------
        case AxisState::HOMING_TO_FAR:
            if (farLimitTriggered()) {
                long curPhys = _stepper.currentPosition() - _zeroOffsetSteps;
                _measuredLengthMm = (float)curPhys / _stepsPerMm;
                _calibrated = true;

                // Hard stop at the switch.
                _stepper.setSpeed(0);

                // Then schedule a smooth accelerated trip to center, from rest.
                long centerPhys  = (long)((_measuredLengthMm / 2.0f) * _stepsPerMm);
                long centerAccel = centerPhys + _zeroOffsetSteps;
                _stepper.setMaxSpeed(GK_CAL_MOVE_SPEED);
                _stepper.setAcceleration(GK_CAL_MOVE_ACCELERATION);
                _stepper.moveTo(centerAccel);
                _setState(AxisState::MOVE_TO_CENTER);

                Serial.print(F("[AXIS] FAR found. Length = "));
                Serial.print(_measuredLengthMm, 1);
                Serial.print(F(" mm. Moving to center ("));
                Serial.print(_measuredLengthMm / 2.0f, 1);
                Serial.println(F(" mm)..."));
            } else if (homeLimitTriggered() &&
                       (_stepper.currentPosition() - _zeroOffsetSteps) > (long)(GK_BACKOFF_MM * _stepsPerMm * 2.0f)) {
                // HOME hit AFTER we've moved at least 2x backoff away — that's
                // a real wiring/direction problem (we're hitting HOME while
                // supposedly heading toward FAR). Below this distance the
                // switch is just still pressed from the moment we found it.
                emergencyStop();
                _setState(AxisState::FAULT);
                Serial.println(F("[AXIS] FAULT: HOME hit during FAR search (check direction)"));
            } else {
                _stepper.run();
            }
            break;

        // ---------- Phase 3: smooth move to center ----------
        case AxisState::MOVE_TO_CENTER:
            if (_stepper.distanceToGo() == 0) {
                _stepper.setMaxSpeed(_maxSpeed);
                _stepper.setAcceleration(GK_RUNTIME_ACCELERATION);
                _setState(AxisState::HOMED);
                Serial.println(F("[AXIS] Ready (HOMED at center)."));
            } else {
                _stepper.run();
            }
            break;

        case AxisState::HOMED:
            break;

        // ---------- Decelerating to a controlled stop ----------
        // Entered when stop() is called (e.g. joystick released). The motor
        // is decelerating per AccelStepper's profile; we keep stepping it
        // until it actually arrives at rest, then transition to HOMED.
        case AxisState::STOPPING:
            _stepper.run();
            if (_stepper.distanceToGo() == 0) {
                _setState(AxisState::HOMED);
            }
            break;

        // ---------- Normal motion ----------
        case AxisState::RUNNING: {
            long curPhys = _stepper.currentPosition() - _zeroOffsetSteps;
            long tgtPhys = _stepper.targetPosition()  - _zeroOffsetSteps;
            bool movingTowardHome = (tgtPhys < curPhys);
            bool movingTowardFar  = (tgtPhys > curPhys);

            // -- HOME limit hit while moving toward home: HARD STOP --
            if (homeLimitTriggered() && movingTowardHome) {
                // Define current physical position as logical 0.
                _zeroOffsetSteps = _stepper.currentPosition();
                // Hard stop: zero velocity AND zero target distance. The
                // carriage is already at the mechanical stop, so any "missed"
                // steps from inertia have nowhere to go anyway. Decelerating
                // smoothly here would just push the carriage harder into
                // the switch.
                _stepper.setSpeed(0);
                _stepper.moveTo(_stepper.currentPosition());
                _homeLatched = true;
                _farLatched  = false;
                _setState(AxisState::HOMED);
                Serial.println(F("[AXIS] HOME limit hit. Re-zeroed."));
                break;
            }

            // -- FAR limit hit while moving toward far: HARD STOP --
            if (_farLimitPin != 255 && farLimitTriggered() && movingTowardFar) {
                long curPhysical  = _stepper.currentPosition() - _zeroOffsetSteps;
                long farPhysical  = (long)(_measuredLengthMm * _stepsPerMm);
                _zeroOffsetSteps += (curPhysical - farPhysical);
                _stepper.setSpeed(0);
                _stepper.moveTo(_stepper.currentPosition());
                _farLatched  = true;
                _homeLatched = false;
                _setState(AxisState::HOMED);
                Serial.print(F("[AXIS] FAR limit hit. Snapped to "));
                Serial.print(_measuredLengthMm, 1);
                Serial.println(F(" mm."));
                break;
            }

            _stepper.run();
            if (_stepper.distanceToGo() == 0) {
                _setState(AxisState::HOMED);
            }
            break;
        }

        // ---------- Constant-velocity motion (joystick, NO acceleration) ----------
        case AxisState::VELOCITY: {
            bool movingTowardHome = (_velStepsPerSec < 0);
            bool movingTowardFar  = (_velStepsPerSec > 0);

            // HOME limit hit while heading home: hard stop, re-zero, latch.
            if (homeLimitTriggered() && movingTowardHome) {
                _zeroOffsetSteps = _stepper.currentPosition();
                _stepper.setSpeed(0);
                _velStepsPerSec = 0;
                _homeLatched = true;
                _farLatched  = false;
                _setState(AxisState::HOMED);
                Serial.println(F("[AXIS] HOME limit hit. Re-zeroed."));
                break;
            }

            // FAR limit hit while heading far: snap to measured length, latch.
            if (_farLimitPin != 255 && farLimitTriggered() && movingTowardFar) {
                long curPhysical = _stepper.currentPosition() - _zeroOffsetSteps;
                long farPhysical = (long)(_measuredLengthMm * _stepsPerMm);
                _zeroOffsetSteps += (curPhysical - farPhysical);
                _stepper.setSpeed(0);
                _velStepsPerSec = 0;
                _farLatched  = true;
                _homeLatched = false;
                _setState(AxisState::HOMED);
                Serial.print(F("[AXIS] FAR limit hit. Snapped to "));
                Serial.print(_measuredLengthMm, 1);
                Serial.println(F(" mm."));
                break;
            }

            _stepper.runSpeed();   // constant velocity — no accel profile
            break;
        }
    }
}

// =============================================================================
// Calibration kickoff — start hunting toward home using accelerated move
// =============================================================================
void StepperAxis::home() {
    Serial.println(F("[AXIS] Calibration started: searching for HOME..."));
    enable();
    _calibrated  = false;
    _homeLatched = false;
    _farLatched  = false;

    _stepper.setMaxSpeed(GK_CAL_HUNT_SPEED);
    _stepper.setAcceleration(GK_CAL_HUNT_ACCELERATION);
    _stepper.moveTo(_stepper.currentPosition() - HUNT_TARGET_STEPS);
    _setState(AxisState::HOMING_TO_HOME);
}

// Legacy helper — kept for header compat but no longer used.
void StepperAxis::_startHomingToward(int8_t direction) {
    _stepper.setMaxSpeed(GK_CAL_HUNT_SPEED);
    _stepper.setAcceleration(GK_CAL_HUNT_ACCELERATION);
    long delta = (direction > 0 ? +HUNT_TARGET_STEPS : -HUNT_TARGET_STEPS);
    _stepper.moveTo(_stepper.currentPosition() + delta);
}

// =============================================================================
// Move commands — translate physical position <-> AccelStepper internal frame
// =============================================================================
void StepperAxis::moveTo(float mm) {
    if (!isHomed()) return;

    long targetPhys = (long)(mm * _stepsPerMm);
    long targetAcc  = targetPhys + _zeroOffsetSteps;
    long curAcc     = _stepper.currentPosition();

    if (targetAcc < curAcc) {
        if (_homeLatched) return;
        _farLatched = false;
    } else if (targetAcc > curAcc) {
        if (_farLatched) return;
        _homeLatched = false;
    } else {
        return;
    }

    _stepper.moveTo(targetAcc);
    _setState(AxisState::RUNNING);
}

void StepperAxis::moveBy(float mm) {
    moveTo(getPositionMm() + mm);
}

// =============================================================================
// Direct velocity control — NO acceleration ramp (joystick manual mode)
// =============================================================================
void StepperAxis::setVelocity(float stepsPerSec) {
    if (!isHomed()) return;

    // Clamp magnitude to the motor ceiling.
    if (stepsPerSec >  _maxSpeed) stepsPerSec =  _maxSpeed;
    if (stepsPerSec < -_maxSpeed) stepsPerSec = -_maxSpeed;

    // Near zero -> stop.
    if (fabs(stepsPerSec) < 1.0f) { _endVelocity(); return; }

    // Respect latches; clear the opposite latch when moving away from it.
    if (stepsPerSec < 0.0f) {              // toward HOME
        if (_homeLatched) { _endVelocity(); return; }
        _farLatched = false;
    } else {                               // toward FAR
        if (_farLatched) { _endVelocity(); return; }
        _homeLatched = false;
    }

    enable();                              // re-energise (HOMED auto-disables)
    _velStepsPerSec = stepsPerSec;
    _stepper.setSpeed(stepsPerSec);        // signed; runSpeed() uses it directly
    _setState(AxisState::VELOCITY);
}

void StepperAxis::_endVelocity() {
    _velStepsPerSec = 0;
    _stepper.setSpeed(0);
    if (_state == AxisState::VELOCITY) _setState(AxisState::HOMED);
}

void StepperAxis::stop() {
    // Velocity mode stops instantly — there is no accel ramp to unwind.
    if (_state == AxisState::VELOCITY) { _endVelocity(); return; }

    // Accel (position) mode: schedule a graceful decel. Enter STOPPING so
    // update() keeps calling _stepper.run() until the motor comes to rest.
    _stepper.stop();
    if (_state == AxisState::RUNNING) _setState(AxisState::STOPPING);
}

void StepperAxis::emergencyStop() {
    _stepper.setCurrentPosition(_stepper.currentPosition());
    _stepper.stop();
}

// =============================================================================
// Driver power
// =============================================================================
void StepperAxis::enable() {
    if (_enaPin != 255 && !_enabled) {
        digitalWrite(_enaPin, STEPPER_ENABLE);
        _enabled = true;
    }
}

void StepperAxis::disable() {
    if (_enaPin != 255 && _enabled) {
        _stepper.stop();
        digitalWrite(_enaPin, STEPPER_DISABLE);
        _enabled = false;
    }
}

void StepperAxis::setMaxSpeedRuntime(float stepsPerSec) {
    if (stepsPerSec > _maxSpeed) stepsPerSec = _maxSpeed;
    if (stepsPerSec < 1.0f)      stepsPerSec = 1.0f;
    _stepper.setMaxSpeed(stepsPerSec);
}

void StepperAxis::adoptPositionMm(float mm) {
    // Adjust the offset rather than calling _stepper.setCurrentPosition().
    long desiredPhys = (long)(mm * _stepsPerMm);
    long curPhys     = _stepper.currentPosition() - _zeroOffsetSteps;
    long delta       = curPhys - desiredPhys;
    _zeroOffsetSteps += delta;
}

void StepperAxis::setHomedPretend() {
    _stepper.setCurrentPosition(0);
    _zeroOffsetSteps = 0;
    _stepper.setMaxSpeed(_maxSpeed);
    _stepper.setAcceleration(GK_RUNTIME_ACCELERATION);
    _measuredLengthMm = _axisLengthMm;
    _calibrated  = true;
    _homeLatched = false;
    _farLatched  = false;
    _setState(AxisState::HOMED);
}

void StepperAxis::clearFault() {
    if (_state == AxisState::FAULT) {
        _stepper.stop();
        _setState(AxisState::UNINIT);
        Serial.println(F("[AXIS] Fault cleared. Re-home before moving."));
    }
}

// =============================================================================
// Status
// =============================================================================
float StepperAxis::getPositionMm() {
    return (float)(_stepper.currentPosition() - _zeroOffsetSteps) / _stepsPerMm;
}

float StepperAxis::getTargetMm() {
    return (float)(_stepper.targetPosition()  - _zeroOffsetSteps) / _stepsPerMm;
}

bool  StepperAxis::isMoving() {
    if (_state == AxisState::VELOCITY) return _velStepsPerSec != 0.0f;
    return _stepper.distanceToGo() != 0;
}

bool  StepperAxis::homeLimitTriggered() { return _readPin(_homeLimitPin); }
bool  StepperAxis::farLimitTriggered()  {
    return _farLimitPin != 255 && _readPin(_farLimitPin);
}

const char* StepperAxis::stateStr() const {
    switch (_state) {
        case AxisState::UNINIT:            return "UNINIT";
        case AxisState::HOMING_TO_HOME:    return "HOMING_HOME";
        case AxisState::BACKOFF_FROM_HOME: return "BACKOFF_HOME";
        case AxisState::HOMING_TO_FAR:     return "HOMING_FAR";
        case AxisState::MOVE_TO_CENTER:    return "TO_CENTER";
        case AxisState::HOMED:             return "HOMED";
        case AxisState::RUNNING:           return "RUNNING";
        case AxisState::VELOCITY:          return "VELOCITY";
        case AxisState::STOPPING:          return "STOPPING";
        case AxisState::FAULT:             return "FAULT";
    }
    return "UNKNOWN";
}

bool StepperAxis::_readPin(uint8_t pin) const {
    return digitalRead(pin) == LIMIT_TRIGGERED;
}

void StepperAxis::_setState(AxisState s) {
    _state = s;
}