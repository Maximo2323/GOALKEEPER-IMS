#pragma once

#include "StepperAxis.h"

// =============================================================================
// JoystickAxis — speed-proportional joystick control with proper acceleration
// =============================================================================
// Strategy:
//   - Reads joystick every JOY_UPDATE_MS.
//   - Inside deadband -> stops the axis and disables the driver.
//   - Outside deadband -> enables driver, sets maxSpeed proportional to
//     |deflection|, and commands a target far past the end of travel so the
//     limit switches stop motion (not the digital limit).
//   - **Only re-issues moveTo() when the requested speed has changed by more
//     than JOY_SPEED_CHANGE_THRESHOLD.** This is critical for acceleration:
//     AccelStepper needs uninterrupted runs of the same target to ramp speed
//     up smoothly. Constantly re-issuing moveTo() resets the trajectory and
//     prevents the accel profile from completing.
//
// Acceleration is set on the underlying AccelStepper to GK_JOY_ACCELERATION
// during construction; the StepperAxis already configures its base accel,
// but joystick mode overrides it for a tunable feel.
// =============================================================================

class JoystickAxis {
public:
    JoystickAxis(uint8_t joystickPin,
                 StepperAxis& axis,
                 int deadband        = 60,
                 float maxSpeed      = 3000.0f,
                 unsigned long updateMs = 20);

    void update();

    float getDeflection();
    bool  isActive();

private:
    uint8_t       _pin;
    StepperAxis&  _axis;
    int           _deadband;
    float         _maxSpeed;
    unsigned long _updateMs;
    unsigned long _lastUpdateMs;

    bool          _wasActive;
    int8_t        _lastDirection;       // -1, 0, +1
    float         _lastIssuedSpeed;     // last commanded speed; new commands gated by change

    float _rawToDeflection(int raw);
};