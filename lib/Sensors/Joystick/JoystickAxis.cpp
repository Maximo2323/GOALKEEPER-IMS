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
      _wasActive(false)
{}

// =============================================================================
// update — called every loop()
// =============================================================================
void JoystickAxis::update() {
    unsigned long now = millis();
    if (now - _lastUpdateMs < _updateMs) return;
    _lastUpdateMs = now;

    float deflection = getDeflection();    // -1..+1, exactly 0 inside deadband

    // -------------------------------------------------------------------------
    // Inside deadband -> stop. Velocity mode halts instantly (no ramp), and
    // StepperAxis::stop() returns the axis to HOMED, which disables the driver.
    // -------------------------------------------------------------------------
    if (deflection == 0.0f) {
        if (_wasActive) {
            _axis.stop();
            _wasActive = false;
        }
        return;
    }

    // -------------------------------------------------------------------------
    // Outside deadband -> speed proportional to deflection, pushed straight to
    // the axis. setVelocity() handles enable, direction, latches and clamping.
    // -------------------------------------------------------------------------
    _wasActive = true;
    // Negated: physical stick left/right was reversed relative to axis travel.
    _axis.setVelocity(-_maxSpeed * deflection);
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