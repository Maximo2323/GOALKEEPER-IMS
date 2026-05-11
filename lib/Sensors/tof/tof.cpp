/**
 * @file tof.cpp
 * @brief Unified VL53L0X / VL53L1X implementation.
 */

#include "tof.hpp"

ToF::ToF()
    : initialized(false),
      continuous(false),
      distanceMm(INVALID_MM)
{}

bool ToF::begin()
{
    sensor.setTimeout(50);

    if (!sensor.init()) {
        initialized = false;
        return false;
    }

#if TOF_SENSOR_TYPE == TOF_L1X
    sensor.setDistanceMode(VL53L1X::Short);
    sensor.setMeasurementTimingBudget(50000);   // 50 ms
    sensor.startContinuous(50);
#else  // TOF_L0X
    // L0X uses different API names but the concepts map cleanly.
    sensor.setMeasurementTimingBudget(50000);   // 50 ms (us)
    sensor.startContinuous(50);                 // ms
#endif

    continuous  = true;
    initialized = true;

    update();
    return true;
}

void ToF::update()
{
    if (!initialized) return;

#if TOF_SENSOR_TYPE == TOF_L1X
    uint16_t d = sensor.read();
#else
    uint16_t d = sensor.readRangeContinuousMillimeters();
#endif

    if (sensor.timeoutOccurred()) {
        distanceMm = INVALID_MM;
        return;
    }

    distanceMm = d;
}

void ToF::setTimingBudgetMs(uint16_t ms)
{
    if (!initialized) return;
    sensor.setMeasurementTimingBudget((uint32_t)ms * 1000UL);
}

void ToF::setInterMeasurementMs(uint16_t ms)
{
    if (!initialized) return;
    if (continuous) sensor.startContinuous(ms);
}

void ToF::startContinuous(uint16_t periodMs)
{
    if (!initialized) return;
    sensor.startContinuous(periodMs);
    continuous = true;
}

void ToF::stopContinuous()
{
    if (!initialized) return;
    sensor.stopContinuous();
    continuous = false;
}

#if TOF_SENSOR_TYPE == TOF_L1X
void ToF::setDistanceMode(VL53L1X::DistanceMode mode)
{
    if (!initialized) return;
    sensor.setDistanceMode(mode);
}
#endif