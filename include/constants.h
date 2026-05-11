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
#define GK_MOTOR_MAX_SPEED          650.0f    // steps/sec
#define GK_MOTOR_MAX_ACCELERATION   3000.0f    // steps/sec^2


// =============================================================================
// STEPPER AXIS — runtime defaults (used by direct moveTo() commands)
// =============================================================================
#define GK_MAX_SPEED        GK_MOTOR_MAX_SPEED
#define GK_ACCELERATION     400.0f


// =============================================================================
// STEPPER AXIS — calibration sequence
// =============================================================================
// HUNT: constant-velocity search for limit switches.
#define GK_CAL_HUNT_SPEED           120.0f    // steps/sec while hunting
#define GK_CAL_HUNT_ACCELERATION    50.0f   // ramp-up to hunt speed

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
// pin -> button -> VCC, INPUT_PULLUP -> pressed reads HIGH
// =============================================================================
#define LIMIT_TRIGGERED     HIGH


// =============================================================================
// JOYSTICK
// =============================================================================
// Joystick-controlled motion: top speed at full deflection + acceleration.
#define GK_JOY_MAX_SPEED                GK_MAX_SPEED
#define GK_JOY_ACCELERATION             3000.0f

// Joystick reading
#define JOY_DEADBAND                    60        // ADC units around center (~512)
#define JOY_UPDATE_MS                   20        // poll period (50 Hz)
#define JOY_MAX_SPEED                   GK_JOY_MAX_SPEED
#define JOY_SPEED_CHANGE_THRESHOLD      0.10f     // re-issue moveTo only above 10% delta


// =============================================================================
// SOLENOID KICKER
// =============================================================================
// MOSFET polarity (low-side N-MOSFET, active-HIGH gate)
#define SOL_FIRE_LEVEL      HIGH
#define SOL_OFF_LEVEL       LOW

// Timing
#define SOL_PULSE_MS        50      // kick duration
#define SOL_COOLDOWN_MS     800     // cap recharge window (rejects re-fire)
#define SOL_MAX_ON_MS       250     // hard safety cap; must be > SOL_PULSE_MS

// Fire button: pin -> button -> VCC, INPUT_PULLUP -> pressed reads HIGH
#define SOL_BUTTON_PRESSED  HIGH


// =============================================================================
// MODE TOGGLE SWITCH (manual / auto)
// =============================================================================
#define MODE_PRESSED_LEVEL  HIGH    // closed -> MANUAL


// =============================================================================
// CAMERA YAW STEPPER (placeholder, not yet wired)
// =============================================================================
#define CAM_STEPS_PER_DEG   (400.0f / 360.0f)
#define CAM_MAX_SPEED       2000.0f
#define CAM_ACCELERATION    5000.0f


// =============================================================================
// RANGE SENSOR (position cross-check) — pick ONE sensor + mount geometry
// =============================================================================
// Which physical sensor:
#define RANGE_TOF           0
#define RANGE_ULTRASONIC    1
#define RANGE_SENSOR_TYPE   RANGE_ULTRASONIC

// Where it's mounted (looking at the carriage):
#define MOUNT_HOME_END      0
#define MOUNT_FAR_END       1
#define RANGE_SENSOR_MOUNT  MOUNT_HOME_END

// Physical geometry (measure on real robot)
#define RANGE_SENSOR_OFFSET_MM      30.0f       // sensor-to-carriage gap at home
#define BAR_LENGTH_MM               560.0f      // total bar length (>= travel)

// Cross-check tuning
#define RANGE_CORRECT_THRESHOLD_MM  3.0f        // re-zero stepper if disagreement > this
#define RANGE_EMA_ALPHA             0.7f        // sensor smoothing (0=raw, 1=frozen)
#define RANGE_CHECK_PERIOD_MS       100         // cross-check rate


// =============================================================================
// ULTRASONIC (HC-SR04) — used only if RANGE_SENSOR_TYPE == RANGE_ULTRASONIC
// =============================================================================
#define US_PING_PERIOD_MS   60      // >= 60 ms per datasheet
#define US_TRIG_HIGH_US     10      // datasheet trigger pulse width
#define US_ECHO_TIMEOUT_US  23200   // ~4 m round trip max


// =============================================================================
// TIME-OF-FLIGHT (Pololu VL53L0X / VL53L1X) — used only if RANGE_SENSOR_TYPE == RANGE_TOF
// =============================================================================
#define TOF_L0X             0
#define TOF_L1X             1
#define TOF_SENSOR_TYPE     TOF_L1X