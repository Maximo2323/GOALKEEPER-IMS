#ifndef LIMIT_SWITCH_HPP
#define LIMIT_SWITCH_HPP

#include <Arduino.h>

class LimitSwitch
{
public:

    LimitSwitch(uint8_t pin, bool inverted = false);

    void begin();
    void update();

    bool isPressed() const { return pressed; }

    // returns true only when switch is newly pressed
    bool wasPressed();

private:

    uint8_t pin;
    bool inverted;

    bool pressed;
    bool lastPressed;
};

#endif