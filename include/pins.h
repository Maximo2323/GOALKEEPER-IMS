#pragma once

// =============================================================================
// GOALKEEPER ROBOT — PIN ASSIGNMENTS (Arduino Uno)
// =============================================================================
// All hardware pin numbers live here. Tuning values, calibration, and timing
// are in constants.h.
//
// Layout (in pin order) — matches the physical wiring on the project:
//   D2  LIMIT_FAR    far  limit switch (pull-down - pressed HIGH)
//   D3  LIMIT_HOME   home limit switch (pull-down - pressed HIGH)
//   D4  BTN_FIRE     fire button       (pull-down - pressed HIGH)
//   D5  BTN_MODE     mode button       (pull-down - pressed HIGH)
//   D6  DIR          stepper driver direction
//   D7  STEP         stepper driver step pulse
//   D8  ENA          stepper driver enable (active-LOW)
//   D9  SOL_MOSFET   solenoid gate (active-HIGH)
//   A0  JOY          joystick X (analog)
// =============================================================================

// -----------------------------------------------------------------------------
// STEPPER: GOALKEEPER AXIS
// -----------------------------------------------------------------------------
#define GK_ENA_PIN          8               // active-LOW (LED on = enabled)
#define GK_STEP_PIN         7
#define GK_DIR_PIN          6

// -----------------------------------------------------------------------------
// BUTTONS
// -----------------------------------------------------------------------------
#define BTN_FIRE_PIN        4               // fire kick
#define BTN_MODE_PIN        5               // manual / auto toggle

// Aliases used by the Solenoid library + legacy code.
#define SOL_BUTTON_PIN      BTN_FIRE_PIN
#define MODE_PIN            BTN_MODE_PIN

// -----------------------------------------------------------------------------
// LIMIT SWITCHES (stepper axis)
// -----------------------------------------------------------------------------
#define GK_LIMIT_HOME_PIN   3
#define GK_LIMIT_FAR_PIN    2

// -----------------------------------------------------------------------------
// SOLENOID KICKER
// -----------------------------------------------------------------------------
#define SOL_MOSFET_PIN      9               // gate of low-side N-MOSFET (active-HIGH)

// -----------------------------------------------------------------------------
// JOYSTICK
// -----------------------------------------------------------------------------
#define JOY_PIN             A0              // analog axis (X)