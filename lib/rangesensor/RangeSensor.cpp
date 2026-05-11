#include "RangeSensor.h"
#include <math.h>

RangeSensor::RangeSensor(StepperAxis& axis)
    : _axis(axis),
      _lastRawMm(0.0f),
      _filteredPosMm(NAN),
      _haveValid(false),
      _lastCheckMs(0)
{}

bool RangeSensor::begin()
{
#if RANGE_SENSOR_TYPE == RANGE_TOF
    return _sensor.begin();
#else
    _sensor.begin();
    return true;   // HC-SR04 has no init failure mode
#endif
}

void RangeSensor::update()
{
    // 1) Pump the underlying driver every loop (state machines, continuous reads).
    _sensor.update();

    // 2) Throttle the rest of the work to RANGE_CHECK_PERIOD_MS.
    unsigned long now = millis();
    if (now - _lastCheckMs < RANGE_CHECK_PERIOD_MS) return;
    _lastCheckMs = now;

    // 3) Pull a reading.
    float raw;
    if (!_readSensor(raw)) {
        // Invalid this cycle — keep last good value, just don't correct.
        return;
    }
    _lastRawMm = raw;

    // 4) Convert reading to stepper-frame position.
    float pos = _readingToPosition(raw);

    // 5) Clamp to legal travel — anything wildly outside is almost certainly noise.
    //    Allow a little overshoot (+/- 20 mm) before rejecting.
    if (pos < -20.0f || pos > _axis.getAxisLengthMm() + 20.0f) {
        return;
    }

    // 6) Filter (EMA). First valid reading seeds the filter.
    if (isnan(_filteredPosMm)) {
        _filteredPosMm = pos;
    } else {
        _filteredPosMm = RANGE_EMA_ALPHA * _filteredPosMm
                       + (1.0f - RANGE_EMA_ALPHA) * pos;
    }
    _haveValid = true;

    // 7) Cross-check & silent re-zero — ONLY when axis is idle (HOMED).
    //    Correcting mid-move would yank AccelStepper's internal target offset
    //    and cause a lurch.
    if (_axis.getState() != AxisState::HOMED) return;
    if (!_axis.isHomed())                     return;   // never seen home yet

    float stepperPos = _axis.getPositionMm();
    float err = _filteredPosMm - stepperPos;

    if (fabs(err) > RANGE_CORRECT_THRESHOLD_MM) {
        // Trust the sensor: shift the stepper's notion of "where I am" by err.
        // This is a silent correction (no Serial print) per your request.
        _axis.adoptPositionMm(_filteredPosMm);
    }
}

void RangeSensor::resetFilter()
{
    _filteredPosMm = NAN;
    _haveValid     = false;
}

// -----------------------------------------------------------------------------
// Geometry: raw distance reading -> position from home (mm)
// -----------------------------------------------------------------------------
float RangeSensor::_readingToPosition(float rawMm) const
{
#if RANGE_SENSOR_MOUNT == MOUNT_HOME_END
    // Sensor at home end, looking outward. Reading = offset + position.
    return rawMm - RANGE_SENSOR_OFFSET_MM;
#else
    // Sensor at far end, looking back. As goalkeeper moves toward home, reading grows.
    // When goalkeeper is at the far end of travel, reading == RANGE_SENSOR_OFFSET_MM.
    // When goalkeeper is at home (pos = 0),         reading == BAR_LENGTH - <carriage_width>
    // We model it as: pos = (BAR_LENGTH - OFFSET) - reading.
    return (BAR_LENGTH_MM - RANGE_SENSOR_OFFSET_MM) - rawMm;
#endif
}

// -----------------------------------------------------------------------------
// Uniform sensor read (handles ToF vs Ultrasonic differences)
// -----------------------------------------------------------------------------
bool RangeSensor::_readSensor(float& outRawMm)
{
#if RANGE_SENSOR_TYPE == RANGE_TOF
    if (!_sensor.isInitialized()) return false;
    uint16_t d = _sensor.getDistanceMm();
    if (d == ToF::INVALID_MM)     return false;
    outRawMm = (float)d;
    return true;
#else
    if (!_sensor.isValid())       return false;
    outRawMm = _sensor.getDistanceMm();
    return true;
#endif
}