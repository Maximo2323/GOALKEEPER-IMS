
#include "limitswitch.hpp"

LimitSwitch::LimitSwitch(uint8_t pin, bool inverted)
    : pin(pin),
      inverted(inverted),
      pressed(false),
      lastPressed(false)
{}

void LimitSwitch::begin()
{
    pinMode(pin, INPUT);
}

void LimitSwitch::update()
{
    lastPressed = pressed;

    bool state = digitalRead(pin);

    if (inverted)
        state = !state;

    pressed = state;
}

bool LimitSwitch::wasPressed()
{
    return (pressed && !lastPressed);
}