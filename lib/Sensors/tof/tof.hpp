/**
 * @file tof.hpp
 * @brief Unified VL53L0X / VL53L1X distance sensor wrapper.
 *
 * Pick the chip in constants.h:
 *   #define TOF_SENSOR_TYPE TOF_L1X   // for VL53L1X
 *   #define TOF_SENSOR_TYPE TOF_L0X   // for VL53L0X
 *
 * Only the selected library is compiled in (saves flash on Uno).
 */

#ifndef TOF_HPP
#define TOF_HPP

#include <Arduino.h>
#include <Wire.h>
#include "constants.h"

#if TOF_SENSOR_TYPE == TOF_L1X
    #include <VL53L1X.h>
    typedef VL53L1X ToFSensor;
#elif TOF_SENSOR_TYPE == TOF_L0X
    #include <VL53L0X.h>
    typedef VL53L0X ToFSensor;
#else
    #error "TOF_SENSOR_TYPE must be TOF_L0X or TOF_L1X (see constants.h)"
#endif

class ToF
{
public:
    static constexpr uint16_t INVALID_MM = 0xFFFF;

    ToF();

    bool begin();
    void update();

    uint16_t getDistanceMm() const { return distanceMm; }
    bool     isInitialized() const { return initialized; }

    // Timing budget in ms (per-measurement integration time).
    void setTimingBudgetMs(uint16_t ms);

    // Time between measurements in continuous mode. Must be >= timing budget.
    void setInterMeasurementMs(uint16_t ms);

    void startContinuous(uint16_t periodMs = 50);
    void stopContinuous();

#if TOF_SENSOR_TYPE == TOF_L1X
    // Only meaningful for L1X: Short / Medium / Long
    void setDistanceMode(VL53L1X::DistanceMode mode);
#endif

private:
    ToFSensor sensor;
    bool      initialized;
    bool      continuous;
    uint16_t  distanceMm;
};

#endif // TOF_HPP