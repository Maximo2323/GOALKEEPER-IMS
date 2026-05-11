#include "JoystickAxis.h"
#include "constants.h"
#include <math.h>

JoystickAxis::JoystickAxis(uint8_t joystickPin,
                           StepperAxis& axis,
                           int deadband,
                           float maxSpeed,
                           unsigned long updateMs)
    : _pin(joystickPin),
      _axis(axis),
      _deadband(deadband),
      _maxSpeed(maxSpeed),
      _updateMs(updateMs),
      _lastUpdateMs(0),
      _wasActive(false),
      _lastDirection(0),
      _lastIssuedSpeed(0.0f)
{}

// =============================================================================
// update — called every loop()
// =============================================================================
void JoystickAxis::update() {
    unsigned long now = millis();
    if (now - _lastUpdateMs < _updateMs) return;
    _lastUpdateMs = now;

    float deflection = getDeflection();

    // -------------------------------------------------------------------------
    // Inside deadband: schedule decel, but don't cut power until motor stops.
    // The motor needs coil current during deceleration to apply braking
    // torque. Disabling immediately would let the motor coast / jerk to a
    // halt depending on detent torque and load.
    // -------------------------------------------------------------------------
    if (deflection == 0.0f) {
        if (_wasActive) {
            // Tell the axis to decelerate to a stop. Do NOT disable yet.
            _axis.stop();
            _wasActive       = false;
            _lastDirection   = 0;
            _lastIssuedSpeed = 0.0f;
            // Driver will be disabled below once isMoving() returns false.
        }
        // Even after _wasActive flips to false, we keep watching for motion
        // to end before cutting power. Once at rest -> disable.
        if (!_axis.isMoving() && _axis.isEnabled()) {
            _axis.disable();
        }
        return;
    }

    // -------------------------------------------------------------------------
    // Outside deadband: enable driver if needed
    // -------------------------------------------------------------------------
    if (!_wasActive) {
        _axis.enable();
        _wasActive = true;
    }

    int8_t newDir = (deflection > 0.0f) ? +1 : -1;
    float  newSpeed = _maxSpeed * fabs(deflection);

    // Direction change always requires a new moveTo() (target sign flips).
    bool directionChanged = (newDir != _lastDirection);

    // Speed change is only "significant" if it crosses a threshold. Smaller
    // changes are absorbed silently so AccelStepper can finish ramping.
    float speedDelta = fabs(newSpeed - _lastIssuedSpeed);
    bool  speedChangedSignificantly =
        (speedDelta / _maxSpeed) > JOY_SPEED_CHANGE_THRESHOLD;

    if (!directionChanged && !speedChangedSignificantly) {
        // Joystick hasn't moved enough — let AccelStepper keep doing its thing.
        return;
    }

    // ---- Issue a new commanded move ----
    _axis.setMaxSpeedRuntime(newSpeed);

    // Generous overshoot so limit switches (not digital limits) stop motion.
    const float overshoot = _axis.getMeasuredLengthMm() + 1000.0f;
    if (newDir > 0) {
        _axis.moveTo(overshoot);
    } else {
        _axis.moveTo(-overshoot);
    }

    _lastDirection   = newDir;
    _lastIssuedSpeed = newSpeed;
}

// =============================================================================
float JoystickAxis::getDeflection() {
    return _rawToDeflection(analogRead(_pin));
}

bool JoystickAxis::isActive() {
    return getDeflection() != 0.0f;
}

float JoystickAxis::_rawToDeflection(int raw) {
    const int center = 512;
    int offset = raw - center;

    if (offset > -_deadband && offset < _deadband) return 0.0f;

    if (offset > 0) {
        return (float)(offset - _deadband) / (float)(511 - _deadband);
    } else {
        return (float)(offset + _deadband) / (float)(511 - _deadband);
    }
}