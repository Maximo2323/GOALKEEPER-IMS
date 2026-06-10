#pragma once

#include "pins.h"   // so existing #include "constants.h" still gets pin defs

// =============================================================================
// GOALKEEPER ROBOT — TUNING & CONFIGURATION
// Pins live in pins.h. This file holds geometry, speeds, polarity, sensors.
// =============================================================================


// -----------------------------------------------------------------------------
// SERIAL
// -----------------------------------------------------------------------------
#define SERIAL_BAUD         115200


// =============================================================================
// STEPPER AXIS — geometry
// =============================================================================
#define GK_STEPS_PER_MM     10.0f       // half-step, 20T GT2 pulley
#define GK_AXIS_LENGTH_MM   500.0f      // initial estimate; overwritten by calibration


// =============================================================================
// STEPPER AXIS — motor ceilings (DO NOT EXCEED)
// Above these the motor stalls / loses steps.
// =============================================================================
#define GK_MOTOR_MAX_SPEED          750.0f    // steps/sec
#define GK_MOTOR_MAX_ACCELERATION   3000.0f   // steps/sec^2


// =============================================================================
// STEPPER AXIS — runtime defaults (used by direct moveTo() commands)
// =============================================================================
#define GK_MAX_SPEED        GK_MOTOR_MAX_SPEED
#define GK_ACCELERATION     500.0f


// =============================================================================
// STEPPER AXIS — calibration sequence
// =============================================================================
// HUNT: constant-velocity search for limit switches.
#define GK_CAL_HUNT_SPEED           130.0f
#define GK_CAL_HUNT_ACCELERATION    60.0f

// MOVE: accelerated travel post-hunt (e.g. trip to center after FAR found).
#define GK_CAL_MOVE_SPEED           500.0f
#define GK_CAL_MOVE_ACCELERATION    700.0f

// BACKOFF: short snap off the limit switch (currently unused; kept for tuning).
#define GK_CAL_BACKOFF_ACCELERATION 15000.0f
#define GK_BACKOFF_MM               5.0f


// =============================================================================
// STEPPER DRIVER — ENA pin polarity (A4988 / DRV8825 / TMC2208 are active-LOW)
// =============================================================================
#define STEPPER_ENABLE      LOW
#define STEPPER_DISABLE     HIGH


// =============================================================================
// LIMIT SWITCHES — wiring polarity
// Wiring: GND - resistor - pin  switch - VCC (pull-down)
// Idle = LOW, triggered = HIGH
// =============================================================================
#define LIMIT_TRIGGERED     HIGH


// =============================================================================
// JOYSTICK — direct velocity control (NO acceleration ramp)
// =============================================================================
// Manual mode maps stick deflection straight to stepper speed: the further you
// push, the faster it goes, with instant response (AccelStepper runSpeed()).
#define JOY_DEADBAND        60              // ADC units around center (~512) = stop
#define JOY_UPDATE_MS       20              // joystick poll period (ms, 50 Hz)
#define JOY_MAX_SPEED       GK_MAX_SPEED    // stepper speed at full deflection (steps/s)

// Acceleration applies ONLY to position (vision) moveTo() targets — the
// joystick path is pure constant-velocity and ignores this.
#define GK_RUNTIME_ACCELERATION   3000.0f


// =============================================================================
// SOLENOID KICKER
// =============================================================================
// MOSFET polarity (low-side N-MOSFET, active-HIGH gate)
#define SOL_FIRE_LEVEL      HIGH
#define SOL_OFF_LEVEL       LOW

// Timing
#define SOL_PULSE_MS        50      // kick duration
#define SOL_COOLDOWN_MS     150     // cap recharge window (rejects re-fire)
#define SOL_MAX_ON_MS       250     // hard safety cap; must be  SOL_PULSE_MS


// =============================================================================
// BUTTONS — wiring polarity
// Wiring: GND - resistor - pin - button - VCC (pull-down)
// Idle = LOW, pressed = HIGH
// =============================================================================
#define SOL_BUTTON_PRESSED  HIGH
#define MODE_PRESSED_LEVEL  HIGH