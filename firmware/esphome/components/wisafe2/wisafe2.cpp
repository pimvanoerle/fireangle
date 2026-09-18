#include "wisafe2.h"
#include "esphome/core/log.h"

#include <inttypes.h>

namespace esphome {
namespace wisafe2 {

static const char *const TAG = "wisafe2";

// ---------------------------------------------------------------- Event ----

static std::string hex24(uint32_t v) {
  char buf[7];
  snprintf(buf, sizeof(buf), "%06x", v & 0xFFFFFF);
  return std::string(buf);
}

static std::string hex16(uint16_t v) {
  char buf[5];
  snprintf(buf, sizeof(buf), "%04x", v);
  return std::string(buf);
}

std::string Event::device_hex() const { return hex24(this->device); }
std::string Event::model_hex() const { return hex16(this->model); }

std::string Event::trigger_name() const {
  switch (this->trigger) {
    case TRIGGER_SMOKE: return "SMOKE";
    case TRIGGER_HEAT: return "HEAT";
    case TRIGGER_CO: return "CARBON MONOXIDE";
    case TRIGGER_ALL: return "ALL";
    default: return "UNKNOWN";
  }
}

std::string Event::kind_name() const {
  switch (this->kind) {
    case EVENT_TEST: return "TEST";
    case EVENT_BASE: return "BASE";
    case EVENT_EMERGENCY: return "EMERGENCY";
    case EVENT_SILENCE: return "SILENCE";
    case EVENT_MISSING: return "MISSING";
    default: return "UNKNOWN";
  }
}

std::string Event::describe() const {
  switch (this->kind) {
    case EVENT_EMERGENCY:
      return this->trigger_name() + " EMERGENCY";
    case EVENT_TEST:
      return this->trigger_name() + (this->pass ? " TEST PASS" : " TEST FAIL");
    case EVENT_BASE:
      return this->on_base ? "ON BASE" : "OFF BASE";
    case EVENT_SILENCE:
      return "SILENCE";
    case EVENT_MISSING:
      return "MISSING";
    default:
      return "UNKNOWN";
  }
}

// ----------------------------------------------------------- FrameReader ----

bool FrameReader::feed(uint8_t byte) {
  if (this->resyncing_) {
    if (byte == TERMINATOR)
      this->resyncing_ = false;
    return false;
  }

  this->buf_.push_back(byte);

  if (byte == TERMINATOR) {
    this->frame_ = this->buf_;
    this->buf_.clear();
    return true;
  }

  if (this->buf_.size() > MAX_FRAME) {
    this->buf_.clear();
    this->resyncing_ = true;
    this->desyncs_++;
    ESP_LOGW(TAG, "lost frame sync (%" PRIu32 " total), resynchronising", this->desyncs_);
  }
  return false;
}

// ---------------------------------------------------------------- decode ----

static uint32_t dev_at(const std::vector<uint8_t> &f, size_t i) {
  return (uint32_t(f[i]) << 16) | (uint32_t(f[i + 1]) << 8) | uint32_t(f[i + 2]);
}

static uint16_t model_at(const std::vector<uint8_t> &f, size_t i) {
  return (uint16_t(f[i]) << 8) | uint16_t(f[i + 1]);
}

bool decode_frame(const std::vector<uint8_t> &f, Event *out) {
  if (f.empty() || f.back() != TERMINATOR)
    return false;

  switch (f[0]) {
    case EVENT_TEST: {
      if (f.size() < 11) return false;
      out->kind = EVENT_TEST;
      out->device = dev_at(f, 1);
      out->trigger = f[4];
      out->has_trigger = true;
      out->pass = (f[5] == 0x01);
      out->model = model_at(f, 6);
      // A failed self-test is the alarm reporting a flat battery.
      out->battery_ok = out->pass;
      out->has_battery = true;
      out->on_base = true;
      out->has_base = true;
      return true;
    }
    case EVENT_BASE: {
      if (f.size() < 10) return false;
      const uint8_t status = f[6];
      out->kind = EVENT_BASE;
      out->device = dev_at(f, 1);
      out->model = model_at(f, 4);
      out->on_base = (status & 0x04) != 0;
      out->has_base = true;
      out->battery_ok = (status & 0x42) == 0;
      out->has_battery = true;
      return true;
    }
    case EVENT_EMERGENCY: {
      if (f.size() < 9) return false;
      out->kind = EVENT_EMERGENCY;
      out->device = dev_at(f, 1);
      out->trigger = f[4];
      out->has_trigger = true;
      out->on_base = true;
      out->has_base = true;
      return true;
    }
    case EVENT_SILENCE: {
      if (f.size() < 5) return false;
      out->kind = EVENT_SILENCE;
      out->device = dev_at(f, 1);
      out->on_base = true;
      out->has_base = true;
      return true;
    }
    case EVENT_MISSING: {
      // The missing device's ID is at offset 6; offset 1 is the peer that noticed.
      if (f.size() < 14) return false;
      out->kind = EVENT_MISSING;
      out->device = dev_at(f, 6);
      return true;
    }
    default:
      return false;
  }
}

// ------------------------------------------------------------- Component ----

void Wisafe2Component::set_pins(InternalGPIOPin *ss, InternalGPIOPin *sck, InternalGPIOPin *sdi,
                                InternalGPIOPin *sdo, InternalGPIOPin *irq) {
  this->ss_pin_ = ss;
  this->sck_pin_ = sck;
  this->sdi_pin_ = sdi;
  this->sdo_pin_ = sdo;
  this->irq_pin_ = irq;
}

void Wisafe2Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up WiSafe2 bridge...");

  this->ss_pin_->setup();
  this->sck_pin_->setup();
  this->sdi_pin_->setup();
  this->sdo_pin_->setup();
  this->irq_pin_->setup();
  this->irq_pin_->digital_write(false);

  // TODO(hardware): the radio is the SPI master and frames every byte in its own _SS
  // cycle. Implement the bit-banged slave shifter here once SCK has been measured --
  // see docs/hardware.md "The ESP32 SPI-slave problem". Until then this component
  // builds and registers entities but receives nothing.

  // The radio needs a moment to stabilise before it will answer an init.
  this->set_timeout("init", 5000, [this]() {
    this->radio_ready_ = this->init_radio_();
    if (!this->radio_ready_) {
      ESP_LOGE(TAG, "radio did not respond to init");
      this->status_set_error(LOG_STR("radio init failed"));
    } else {
      ESP_LOGI(TAG, "radio init OK");
      this->status_clear_error();
    }
  });
}

bool Wisafe2Component::init_radio_() {
  static const uint8_t INIT[] = {0xD3, 0x19, 0x50, 0x00, 0x7E};
  return this->send_command_(INIT, sizeof(INIT), true);
}

void Wisafe2Component::loop() {
  uint8_t byte;
  while (this->read_byte_from_radio_(&byte)) {
    if (this->reader_.feed(byte))
      this->handle_frame_();
  }
}

void Wisafe2Component::handle_frame_() {
  const auto &frame = this->reader_.frame();
  this->last_frame_ms_ = millis();

  if (this->raw_mode_) {
    std::string hex;
    for (uint8_t b : frame) {
      char buf[4];
      snprintf(buf, sizeof(buf), "%02X ", b);
      hex += buf;
    }
    ESP_LOGI(TAG, "RAW: %s", hex.c_str());
    return;
  }

  Event event{};
  if (!decode_frame(frame, &event)) {
    ESP_LOGW(TAG, "undecodable frame, length %zu, type 0x%02X", frame.size(),
             frame.empty() ? 0 : frame[0]);
    return;
  }

  ESP_LOGI(TAG, "%s from %s (%s)", event.describe().c_str(), event.device_hex().c_str(),
           event.model_hex().c_str());
  this->publish_(event);
}

void Wisafe2Component::publish_(const Event &event) {
  for (auto *listener : this->listeners_)
    listener->on_event(event);
}

void Wisafe2Component::send_test(uint8_t trigger) {
  const uint8_t d0 = (this->device_id_ >> 16) & 0xFF;
  const uint8_t d1 = (this->device_id_ >> 8) & 0xFF;
  const uint8_t d2 = this->device_id_ & 0xFF;
  const uint8_t m0 = (this->model_id_ >> 8) & 0xFF;
  const uint8_t m1 = this->model_id_ & 0xFF;

  const uint8_t part1[] = {0x70, d0, d1, d2, trigger, 0x01, m0, m1, 0x7E};
  if (!this->send_command_(part1, sizeof(part1), true)) {
    ESP_LOGW(TAG, "test command part 1 failed");
    return;
  }
  const uint8_t part2[] = {0x91, d0, d1, d2, m0, m1, trigger, 0x05, 0x00, 0x01, 0x7E};
  this->send_command_(part2, sizeof(part2), false);
  ESP_LOGI(TAG, "network test broadcast (trigger 0x%02X)", trigger);
}

void Wisafe2Component::send_silence(uint8_t trigger) {
  const uint8_t d0 = (this->device_id_ >> 16) & 0xFF;
  const uint8_t d1 = (this->device_id_ >> 8) & 0xFF;
  const uint8_t d2 = this->device_id_ & 0xFF;
  const uint8_t cmd[] = {0x61, d0, d1, d2, trigger, 0x01, 0x7E};
  this->send_command_(cmd, sizeof(cmd), true);
  ESP_LOGI(TAG, "silence broadcast (trigger 0x%02X)", trigger);
}

void Wisafe2Component::check_pairing() {
  static const uint8_t CMD[] = {0xD3, 0x03, 0x7E};
  this->send_command_(CMD, sizeof(CMD), true);
}

void Wisafe2Component::start_pairing() {
  // Multi-step handshake with a ~20 s join window -- see docs/protocol.md section 3.
  ESP_LOGW(TAG, "pairing not yet implemented");
}

void Wisafe2Component::dump_config() {
  ESP_LOGCONFIG(TAG, "WiSafe2 Bridge:");
  ESP_LOGCONFIG(TAG, "  Device ID: %s", hex24(this->device_id_).c_str());
  ESP_LOGCONFIG(TAG, "  Model ID:  %s", hex16(this->model_id_).c_str());
  ESP_LOGCONFIG(TAG, "  Raw mode:  %s", YESNO(this->raw_mode_));
  LOG_PIN("  SS Pin:   ", this->ss_pin_);
  LOG_PIN("  SCK Pin:  ", this->sck_pin_);
  LOG_PIN("  SDI Pin:  ", this->sdi_pin_);
  LOG_PIN("  SDO Pin:  ", this->sdo_pin_);
  LOG_PIN("  IRQ Pin:  ", this->irq_pin_);
}

// --- SPI slave primitives -- see docs/hardware.md before implementing -------

void Wisafe2Component::write_byte_to_radio_(uint8_t byte) {
  // TODO(hardware): raise IRQ, wait for _SS low, shift `byte` out on SDO under the
  // radio's SCK, wait for _SS high, drop IRQ.
  (void) byte;
}

bool Wisafe2Component::read_byte_from_radio_(uint8_t *out) {
  // TODO(hardware): on _SS falling edge, shift 8 bits in from SDI under the radio's
  // SCK, then pulse IRQ as an ACK. Return false when no byte is pending.
  (void) out;
  return false;
}

bool Wisafe2Component::send_command_(const uint8_t *cmd, size_t len, bool wait_for_reply) {
  for (size_t i = 0; i < len; i++)
    this->write_byte_to_radio_(cmd[i]);

  if (!wait_for_reply)
    return true;

  // Replies are two bytes: 41 7E = ack, 46 7E = accepted for send.
  const uint32_t deadline = millis() + 500;
  uint8_t first = 0;
  bool got_first = false;
  while (millis() < deadline) {
    uint8_t byte;
    if (!this->read_byte_from_radio_(&byte))
      continue;
    if (!got_first) {
      first = byte;
      got_first = true;
    } else if (byte == TERMINATOR) {
      return first == 0x41 || first == 0x46;
    }
  }
  return false;
}

}  // namespace wisafe2
}  // namespace esphome
