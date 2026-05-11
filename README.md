# GOALKEEPER-IMS-PROD

> Autonomous foosball goalkeeper robot — firmware, motion control & vision pipeline.
> Tecnológico de Monterrey · Implementation of Mechatronic Systems · 2026

---

## Overview

This repository contains the full software stack for an autonomous foosball goalkeeper robot. The system mounts a stepper-driven carriage on precision linear rods with a solenoid kicker, designed to react to live ball tracking in real time.

---

## Current State — Firmware (Arduino / PlatformIO)

The C++ firmware is fully modular and operational. Hardware is abstracted into purpose-built libraries, each with a clean, minimal API:

Library & Responsibility
`StepperAxis` | Motion control, calibration, homing |
`JoystickAxis` | Analog joystick input with deadzone |
`Solenoid` | Kicker actuation and timing |
`LimitSwitch` | End-stop detection |
`RangeSensor` | Unified range sensor interface |
`Ultrasonic` | HC-SR04 driver |
`ToF` | VL53L0X/L1X driver |

All tunable parameters are centralized in `constants.h` and `pins.h`, keeping `main.cpp` free of magic numbers. Key motion control features:

- Two-pass limit-switch calibration sequence
- Coordinate-offset homing (avoids mid-motion position resets)
- `STOPPING` deceleration state for smooth transitions
- Threshold-gated joystick `moveTo()` calls to preserve AccelStepper's acceleration profile

## Coming Next — Vision Pipeline (Python / OpenCV)

A computer vision pipeline will track an orange golf ball via webcam and feed position commands to the Arduino over serial, enabling fully autonomous goalkeeper behavior.

**Pipeline stages:**
1. HSV color masking to isolate the ball
2. Hough circle detection for position extraction
3. Kalman filter (`[x, y, radius, vx, vy, vr]` state vector) for smooth, predictive tracking
4. Serial communication to replace/augment joystick input


## Why a GitHub Repo?

Beyond version control, the repo enforces the discipline this project depends on:

- **Separation of concerns** — test code lives in `test/`, never in `src/`
- **Team collaboration** — multiple members can work in parallel without conflicts
- **Living documentation** — commit history captures every hardware bug found and fixed on real hardware, which is as valuable as the code itself

---

## Team

| Name | ID |
| Favio Artea Bretado | A00842128 |
| Yael Guerrero | A00842246 |
| Eduardo Mateo Murillo Andrade | A00842099 |
| Maximo Javier Fajardo Cantú | A01384983 |

> **Course:** Implementation of Mechatronic Systems — Group 607  
> **Professor:** Salvador Alejandro Leal Merlo}
