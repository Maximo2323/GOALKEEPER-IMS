#pragma once

/**
 * @file ultrasonic.hpp
 * @brief HC-SR04 non-blocking state machine.
 *
 * Reads in mm. Same logic as your original; only the constants source changed
 * (now pulls from the project-wide constants.h via #defines, instead of a
 * Constants:: namespace).
 */

#include <Arduino.h>
#include "constants.h"

class Ultrasonic
{
public:
    Ultrasonic(uint8_t trigPin = US_TRIG_PIN, uint8_t echoPin = US_ECHO_PIN);

    void  begin();
    void  update();

    // Distance in mm. Returns last good reading; check isValid() first.
    float getDistanceMm() const;
    bool  isValid()       const;

private:
    enum class State : uint8_t
    {
        Idle,
        Trig_High,
        Wait_Echo_Up,
        Wait_Echo_Down
    };

    uint8_t trig;
    uint8_t echo;

    State    state;
    uint32_t lastPingMs;
    uint32_t trigStartUs;
    uint32_t echoRiseUs;

    float distanceMm;
    bool  valid;

    static constexpr uint32_t pingperiodms  = US_PING_PERIOD_MS;
    static constexpr uint32_t trighighus    = US_TRIG_HIGH_US;
    static constexpr uint32_t echotimeoutus = US_ECHO_TIMEOUT_US;
};