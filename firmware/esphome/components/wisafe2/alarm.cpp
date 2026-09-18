#include "alarm.h"
#include "esphome/core/log.h"

namespace esphome {
namespace wisafe2 {

static const char *const TAG = "wisafe2.alarm";

void Wisafe2Alarm::on_event(const Event &event) {
  if (event.device != this->device_)
    return;

  if (this->event_sensor_ != nullptr)
    this->event_sensor_->publish_state(event.describe());

  // Emergency latches on while the device is in alarm and clears on silence. A MISSING
  // report is not an all-clear -- if a device drops off the mesh mid-alarm we hold the
  // emergency state rather than quietly claiming everything is fine.
  if (this->emergency_sensor_ != nullptr) {
    if (event.is_emergency())
      this->emergency_sensor_->publish_state(true);
    else if (event.kind == EVENT_SILENCE)
      this->emergency_sensor_->publish_state(false);
  }

  // device_class BATTERY is inverted by HA convention: true means "low".
  if (this->battery_sensor_ != nullptr && event.has_battery)
    this->battery_sensor_->publish_state(!event.battery_ok);

  if (this->base_sensor_ != nullptr && event.has_base)
    this->base_sensor_->publish_state(event.on_base);

  ESP_LOGD(TAG, "%s: %s", this->event_sensor_ != nullptr ? this->event_sensor_->get_name().c_str()
                                                         : event.device_hex().c_str(),
           event.describe().c_str());
}

}  // namespace wisafe2
}  // namespace esphome
