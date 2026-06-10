#include "Solenoid.h"

Solenoid::Solenoid(uint8_t mosfetPin, uint8_t buttonPin)
    : _mosfetPin(mosfetPin),
      _buttonPin(buttonPin),
      _state(SolenoidState::IDLE),
      _pulseStartMs(0),
      _cooldownStartMs(0),
      _btnPressed(false),
      _btnLastPressed(false)
{}

void Solenoid::begin()
{
    pinMode(_mosfetPin, OUTPUT);
    _setOutput(SOL_OFF_LEVEL);          // ALWAYS start with coil off

    if (_buttonPin != 255) {
        pinMode(_buttonPin, INPUT);
    }

    _state = SolenoidState::IDLE;
}

void Solenoid::update()
{
    const unsigned long now = millis();

    // -------------------------------------------------------------------------
    // Safety cap — if for ANY reason the gate has been HIGH longer than the
    // hard limit, force it off. Catches stuck-state bugs, dropped events, etc.
    // -------------------------------------------------------------------------
    if (_state == SolenoidState::FIRING &&
        (now - _pulseStartMs) >= SOL_MAX_ON_MS)
    {
        _setOutput(SOL_OFF_LEVEL);
        _cooldownStartMs = now;
        _state = SolenoidState::COOLDOWN;
        // Note: we don't print here so this safety net stays silent; if you
        // want a warning, add Serial.println in main when you observe it.
    }

    // -------------------------------------------------------------------------
    // State machine
    // -------------------------------------------------------------------------
    switch (_state) {
        case SolenoidState::IDLE:
            // Nothing to do until fire() is called.
            break;

        case SolenoidState::FIRING:
            if ((now - _pulseStartMs) >= SOL_PULSE_MS) {
                _setOutput(SOL_OFF_LEVEL);
                _cooldownStartMs = now;
                _state = SolenoidState::COOLDOWN;
            }
            break;

        case SolenoidState::COOLDOWN:
            if ((now - _cooldownStartMs) >= SOL_COOLDOWN_MS) {
                _state = SolenoidState::IDLE;
            }
            break;
    }

    // -------------------------------------------------------------------------
    // Button — fire on rising edge of "pressed" (not while held).
    // -------------------------------------------------------------------------
    _readButton();
    if (_btnPressed && !_btnLastPressed) {
        fire();   // silently rejected if not in IDLE — that's fine
    }
}

bool Solenoid::fire()
{
    if (_state != SolenoidState::IDLE) return false;

    _pulseStartMs = millis();
    _setOutput(SOL_FIRE_LEVEL);
    _state = SolenoidState::FIRING;
    return true;
}

void Solenoid::reset()
{
    _setOutput(SOL_OFF_LEVEL);
    _state = SolenoidState::IDLE;
}

unsigned long Solenoid::timeUntilReady() const
{
    const unsigned long now = millis();
    switch (_state) {
        case SolenoidState::IDLE:
            return 0;
        case SolenoidState::FIRING: {
            unsigned long fireRemaining = SOL_PULSE_MS - (now - _pulseStartMs);
            return fireRemaining + SOL_COOLDOWN_MS;
        }
        case SolenoidState::COOLDOWN: {
            unsigned long elapsed = now - _cooldownStartMs;
            return (elapsed >= SOL_COOLDOWN_MS) ? 0 : (SOL_COOLDOWN_MS - elapsed);
        }
    }
    return 0;
}

void Solenoid::_setOutput(uint8_t level)
{
    digitalWrite(_mosfetPin, level);
}

void Solenoid::_readButton()
{
    if (_buttonPin == 255) {
        _btnLastPressed = false;
        _btnPressed     = false;
        return;
    }
    _btnLastPressed = _btnPressed;
    _btnPressed     = (digitalRead(_buttonPin) == SOL_BUTTON_PRESSED);
}
