#pragma once

#include "StepperAxis.h"

// =============================================================================
// JoystickAxis — speed-proportional manual control (direct velocity, NO accel)
// =============================================================================
// Strategy:
//   - Reads the joystick every JOY_UPDATE_MS.
//   - Inside deadband - stops the axis (instant; there is no ramp).
//   - Outside deadband - commands StepperAxis::setVelocity() with a speed
//     proportional to deflection: speed = JOY_MAX_SPEED * deflection.
//     The further the stick is pushed, the faster the stepper runs, with
//     immediate response (the axis runs it via AccelStepper::runSpeed()).
//
// There is no acceleration profile and no moveTo() gating anymore — every poll
// simply pushes the latest speed to the axis. The limit switches (handled
// inside StepperAxis) still stop motion at the ends of travel.
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

    float _rawToDeflection(int raw);
};