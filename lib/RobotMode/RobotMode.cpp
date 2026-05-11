#include "RobotMode.h"

// =============================================================================
// Constructor
// =============================================================================
RobotMode::RobotMode(uint8_t modePin, StepperAxis& axis, JoystickAxis& joystick)
    : _modePin(modePin),
      _axis(axis),
      _joystick(joystick),
      _mode(RobotModeState::AUTO),
      _lastMode(RobotModeState::AUTO)
{}

// =============================================================================
// init
// =============================================================================
void RobotMode::init() {
    pinMode(_modePin, INPUT_PULLUP);
    _mode = _readSwitch();
    _lastMode = _mode;
    Serial.print(F("[MODE] Starting in: "));
    Serial.println(modeStr());
}

// =============================================================================
// update — call every loop()
// =============================================================================
void RobotMode::update() {
    RobotModeState current = _readSwitch();

    // Detect mode change
    if (current != _lastMode) {
        _onModeChange(current);
        _lastMode = current;
        _mode = current;
    }

    // Delegate to active mode handler
    switch (_mode) {
        case RobotModeState::MANUAL: _handleManual(); break;
        case RobotModeState::AUTO:   _handleAuto();   break;
    }
}

// =============================================================================
// _handleManual — joystick drives the axis
// =============================================================================
void RobotMode::_handleManual() {
    _joystick.update();
}

// =============================================================================
// _handleAuto — placeholder for Pi serial commands (Phase 2)
// =============================================================================
void RobotMode::_handleAuto() {
    // Phase 2: parse serial commands from Pi and call _axis.moveTo()
    // Nothing here yet — axis holds last position
}

// =============================================================================
// _onModeChange — called once when switch flips
// =============================================================================
void RobotMode::_onModeChange(RobotModeState newMode) {
    Serial.print(F("[MODE] Switched to: "));

    if (newMode == RobotModeState::MANUAL) {
        Serial.println(F("MANUAL"));
        // Stop any in-progress auto move when entering manual
        _axis.stop();
    } else {
        Serial.println(F("AUTO"));
        // Stop joystick-driven move when entering auto
        _axis.stop();
    }
}

// =============================================================================
// _readSwitch — reads physical pin
// =============================================================================
RobotModeState RobotMode::_readSwitch() {
    // Switch closed (LOW) → MANUAL, open (HIGH via pullup) → AUTO
    return (digitalRead(_modePin) == LOW)
        ? RobotModeState::MANUAL
        : RobotModeState::AUTO;
}

// =============================================================================
// modeStr
// =============================================================================
const char* RobotMode::modeStr() const {
    switch (_mode) {
        case RobotModeState::MANUAL: return "MANUAL";
        case RobotModeState::AUTO:   return "AUTO";
        default:                     return "UNKNOWN";
    }
}