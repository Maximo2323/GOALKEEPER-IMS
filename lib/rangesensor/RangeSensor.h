#pragma once

#include <Arduino.h>
#include "constants.h"
#include "StepperAxis.h"

#if RANGE_SENSOR_TYPE == RANGE_TOF
    #include "tof.hpp"
#elif RANGE_SENSOR_TYPE == RANGE_ULTRASONIC
    #include "ultrasonic.hpp"
#else
    #error "RANGE_SENSOR_TYPE must be RANGE_TOF or RANGE_ULTRASONIC"
#endif

// =============================================================================
// RangeSensor
// =============================================================================
// Single facade over either the ToF or the HC-SR04. Responsible for:
//   - calling the underlying sensor's update()
//   - converting raw distance reading -> stepper-frame position (mm from home)
//   - low-pass filtering (EMA) to suppress single-ping noise
//   - periodically comparing against StepperAxis.getPositionMm() and silently
//     re-zeroing the stepper when they disagree by more than the threshold,
//     provided the axis is idle and the reading is valid.
//
// Geometry & sensor selection are configured in constants.h.
// =============================================================================

class RangeSensor {
public:
    explicit RangeSensor(StepperAxis& axis);

    bool begin();        // initialise the underlying sensor; returns false on failure
    void update();       // call every loop()

    // Last filtered position estimate, in mm from home. NaN if no valid reading yet.
    float getPositionMm() const { return _filteredPosMm; }

    // Last raw sensor reading in mm (distance, not position). For debug.
    float getRawMm() const { return _lastRawMm; }

    bool  hasValidReading() const { return _haveValid; }

    // Force the filter to resync to the current reading (called after homing
    // so the EMA doesn't lag behind the known-good zero).
    void  resetFilter();

private:
    StepperAxis& _axis;

#if RANGE_SENSOR_TYPE == RANGE_TOF
    ToF        _sensor;
#else
    Ultrasonic _sensor;
#endif

    float _lastRawMm;
    float _filteredPosMm;
    bool  _haveValid;
    unsigned long _lastCheckMs;

    // Convert raw sensor distance -> stepper-frame position (mm from home).
    float _readingToPosition(float rawMm) const;

    // Read the underlying sensor uniformly. Returns false if reading invalid.
    bool  _readSensor(float& outRawMm);
};