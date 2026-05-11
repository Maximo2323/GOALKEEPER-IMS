#pragma once

#include <Arduino.h>
#include "JoystickAxis.h"
#include "StepperAxis.h"

// =============================================================================
// RobotMode
// =============================================================================
// Top-level state machine with two modes:
//
//   MANUAL — joystick controls the goalkeeper axis directly
//   AUTO   — Pi sends GOTO commands over serial (Phase 2)
//
// A physical toggle switch on modePin selects the mode:
//   Switch OPEN   (pin HIGH via pullup) → AUTO
//   Switch CLOSED (pin LOW)             → MANUAL
//
// Usage:
//   RobotMode robot(modePin, goalkeeper, joystick);
//   void loop() { robot.update(); }
// =============================================================================

enum class RobotModeState {
    MANUAL,
    AUTO
};

class RobotMode {
public:
    RobotMode(uint8_t modePin, StepperAxis& axis, JoystickAxis& joystick);

    // Call once in setup()
    void init();

    // Call every loop() — reads switch, delegates to correct handler
    void update();

    RobotModeState getMode() const { return _mode; }
    const char*    modeStr() const;

private:
    uint8_t        _modePin;
    StepperAxis&   _axis;
    JoystickAxis&  _joystick;
    RobotModeState _mode;
    RobotModeState _lastMode;

    void _handleManual();
    void _handleAuto();
    void _onModeChange(RobotModeState newMode);
    RobotModeState _readSwitch();
};