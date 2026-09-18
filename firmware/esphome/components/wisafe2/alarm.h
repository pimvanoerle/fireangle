#pragma once

#include "wisafe2.h"

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"

namespace esphome {
namespace wisafe2 {

// One physical alarm on the mesh. Filters the event stream down to its own device ID and
// fans the result out across its entities.
//
// Entity state is sticky by design: an alarm only transmits when something happens, so
// between events the last known state IS the current state. Nothing here resets to unknown.
class Wisafe2Alarm : public Wisafe2Listener {
 public:
  void set_device(uint32_t device) { this->device_ = device; }
  void set_event_sensor(text_sensor::TextSensor *s) { this->event_sensor_ = s; }
  void set_emergency_sensor(binary_sensor::BinarySensor *s) { this->emergency_sensor_ = s; }
  void set_battery_sensor(binary_sensor::BinarySensor *s) { this->battery_sensor_ = s; }
  void set_base_sensor(binary_sensor::BinarySensor *s) { this->base_sensor_ = s; }

  void on_event(const Event &event) override;

 protected:
  uint32_t device_{0};
  text_sensor::TextSensor *event_sensor_{nullptr};
  binary_sensor::BinarySensor *emergency_sensor_{nullptr};
  binary_sensor::BinarySensor *battery_sensor_{nullptr};
  binary_sensor::BinarySensor *base_sensor_{nullptr};
};

}  // namespace wisafe2
}  // namespace esphome
