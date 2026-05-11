/**
 * @file ultrasonic.cpp
 * @brief HC-SR04 non-blocking ranging.
 *
 * Echo-pulse-to-distance:
 *   speed of sound ~= 343 m/s = 0.343 mm/us.
 *   round-trip distance = pulse_us * 0.343 / 2 = pulse_us / 5.83.
 *   Using 5.8 (your original used 58 for cm; we want mm so divide by 5.8).
 */

#include "ultrasonic.hpp"

Ultrasonic::Ultrasonic(uint8_t trigPin, uint8_t echoPin)
    : trig(trigPin), echo(echoPin),
      state(State::Idle),
      lastPingMs(0), trigStartUs(0), echoRiseUs(0),
      distanceMm(0.0f), valid(false)
{}

void Ultrasonic::begin()
{
    pinMode(trig, OUTPUT);
    pinMode(echo, INPUT);
    digitalWrite(trig, LOW);

    state      = State::Idle;
    lastPingMs = millis();
}

void Ultrasonic::update()
{
    const uint32_t nowMs = millis();
    const uint32_t nowUs = micros();

    switch (state)
    {
        case State::Idle:
            if (nowMs - lastPingMs >= pingperiodms) {
                digitalWrite(trig, HIGH);
                trigStartUs = nowUs;
                state       = State::Trig_High;
            }
            break;

        case State::Trig_High:
            if (nowUs - trigStartUs >= trighighus) {
                digitalWrite(trig, LOW);
                state = State::Wait_Echo_Up;
            }
            break;

        case State::Wait_Echo_Up:
            if (digitalRead(echo) == HIGH) {
                echoRiseUs = nowUs;
                state      = State::Wait_Echo_Down;
            } else if (nowUs - trigStartUs >= echotimeoutus) {
                valid      = false;
                lastPingMs = nowMs;
                state      = State::Idle;
            }
            break;

        case State::Wait_Echo_Down:
            if (digitalRead(echo) == LOW) {
                distanceMm = (nowUs - echoRiseUs) / 5.8f;   // -> millimeters
                valid      = true;
                lastPingMs = nowMs;
                state      = State::Idle;
            } else if (nowUs - echoRiseUs >= echotimeoutus) {
                valid      = false;
                lastPingMs = nowMs;
                state      = State::Idle;
            }
            break;
    }
}

float Ultrasonic::getDistanceMm() const { return distanceMm; }
bool  Ultrasonic::isValid()       const { return valid; }