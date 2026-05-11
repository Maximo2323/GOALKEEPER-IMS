#pragma once

// =============================================================================
// GOALKEEPER ROBOT — PIN ASSIGNMENTS (Arduino Uno)
// =============================================================================
// All hardware pin numbers live here. Tuning values, calibration, and timing
// are in constants.h.
//
// Uno pin map cheat-sheet:
//   D0/D1   : Serial (USB) — DO NOT USE
//   D2      : INT0 (hardware interrupt) — CONSUMED by STEP in this layout
//   D3      : INT1 (hardware interrupt) — CONSUMED by DIR in this layout
//   D10..13 : SPI (only matters if you add SPI peripherals)
//   D13     : on-board LED (avoid for digital inputs)
//   A4/A5   : I2C SDA/SCL (used by ToF sensor)
//   A0..A5  : analog in; also fully usable as digital I/O
//   A6/A7   : analog-input ONLY — cannot do digitalRead/Write
// =============================================================================

// -----------------------------------------------------------------------------
// STEPPER: GOALKEEPER AXIS
// -----------------------------------------------------------------------------
#define GK_STEP_PIN         2
#define GK_DIR_PIN          3
#define GK_ENA_PIN          4               // active-LOW (LED on = enabled)

// Two limit switches: one at home (position 0), one at the far end of travel.
// Both wired to GND with INPUT_PULLUP -> reading LOW = triggered.
#define GK_LIMIT_HOME_PIN   A1
#define GK_LIMIT_FAR_PIN    A2

// Backwards-compat alias (some older code referred to GK_LIMIT_PIN)
#define GK_LIMIT_PIN        GK_LIMIT_HOME_PIN

// -----------------------------------------------------------------------------
// CAMERA YAW STEPPER (placeholder)
// -----------------------------------------------------------------------------
#define CAM_STEP_PIN        6
#define CAM_DIR_PIN         7
#define CAM_LIMIT_PIN       8

// -----------------------------------------------------------------------------
// JOYSTICK
// -----------------------------------------------------------------------------
#define JOY_PIN             A0              // analog axis (X)

// -----------------------------------------------------------------------------
// MODE TOGGLE SWITCH (manual / auto)
// -----------------------------------------------------------------------------
#define MODE_PIN            10

// -----------------------------------------------------------------------------
// SOLENOID KICKER + FIRE BUTTON
// -----------------------------------------------------------------------------
#define SOL_MOSFET_PIN      9               // gate of low-side N-MOSFET (active-HIGH)
                                            // (LED for bench testing on same pin)
#define SOL_BUTTON_PIN      5               // fire button to GND (INPUT_PULLUP)

// -----------------------------------------------------------------------------
// ULTRASONIC (HC-SR04)
// -----------------------------------------------------------------------------
#define US_TRIG_PIN         11
#define US_ECHO_PIN         A3              // free analog pin; A6/A7 cannot do digital

// -----------------------------------------------------------------------------
// I2C (used by ToF) — fixed on Uno
// -----------------------------------------------------------------------------
//   SDA = A4
//   SCL = A5

// =============================================================================
// PIN USAGE MAP (current layout)
// =============================================================================
//   D0   Serial RX     (USB)
//   D1   Serial TX     (USB)
//   D2   STEP          (output, also INT0)
//   D3   DIR           (output, also INT1)
//   D4   ENA           (output, active-LOW)
//   D5   SOL_BUTTON    (input pullup, fire kick)
//   D6   CAM_STEP      (placeholder)
//   D7   CAM_DIR       (placeholder)
//   D8   CAM_LIMIT     (placeholder)
//   D9   SOL_MOSFET    (output, active-HIGH)
//   D10  MODE switch   (input pullup)
//   D11  US_TRIG       (output)
//   D12  -- free --
//   D13  -- free (avoid for inputs, on-board LED) --
//   A0   JOY_PIN       (analog input)
//   A1   GK_LIMIT_HOME (input pullup)
//   A2   GK_LIMIT_FAR  (input pullup)
//   A3   US_ECHO       (digital input)
//   A4   SDA           (I2C, ToF)
//   A5   SCL           (I2C, ToF)
// =============================================================================