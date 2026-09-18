#pragma once

#include "esphome/core/component.h"
#include "esphome/core/hal.h"

#include <map>
#include <string>
#include <vector>

namespace esphome {
namespace wisafe2 {

static const uint8_t TERMINATOR = 0x7E;
static const size_t MAX_FRAME = 25;

// Trigger types. 0x82 is the heat-alarm variant; the reference implementation folds it
// into fire, which loses the smoke/heat distinction. See docs/protocol.md.
enum Trigger : uint8_t {
  TRIGGER_CO = 0x41,
  TRIGGER_SMOKE = 0x81,
  TRIGGER_HEAT = 0x82,
  TRIGGER_ALL = 0xFF,
};

enum EventKind : uint8_t {
  EVENT_TEST = 0x70,
  EVENT_BASE = 0x71,
  EVENT_EMERGENCY = 0x50,
  EVENT_SILENCE = 0x61,
  EVENT_MISSING = 0xD2,
};

struct Event {
  EventKind kind;
  uint32_t device{0};       // 24-bit device ID
  uint16_t model{0};        // 16-bit model ID, 0 when the frame carries none
  uint8_t trigger{0};
  bool has_trigger{false};
  bool pass{true};
  bool on_base{true};
  bool battery_ok{true};
  bool has_battery{false};
  bool has_base{false};

  bool is_emergency() const { return kind == EVENT_EMERGENCY; }
  std::string device_hex() const;
  std::string model_hex() const;
  std::string trigger_name() const;
  std::string kind_name() const;
  // Human-readable state string, e.g. "SMOKE EMERGENCY" or "HEAT TEST PASS".
  std::string describe() const;
};

class Wisafe2Listener {
 public:
  virtual void on_event(const Event &event) = 0;
};

// Reassembles the byte stream from the radio into terminated frames. On losing sync it
// discards up to and including the next terminator rather than gluing garbage onto the
// front of a real frame -- a dropped event is recoverable, a fabricated one is not.
class FrameReader {
 public:
  // Returns true when `frame_` holds a complete frame.
  bool feed(uint8_t byte);
  const std::vector<uint8_t> &frame() const { return frame_; }
  uint32_t desyncs() const { return desyncs_; }

 protected:
  std::vector<uint8_t> buf_;
  std::vector<uint8_t> frame_;
  bool resyncing_{false};
  uint32_t desyncs_{0};
};

bool decode_frame(const std::vector<uint8_t> &frame, Event *out);

class Wisafe2Component : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void set_pins(InternalGPIOPin *ss, InternalGPIOPin *sck, InternalGPIOPin *sdi,
                InternalGPIOPin *sdo, InternalGPIOPin *irq);
  void set_device_id(uint32_t id) { this->device_id_ = id; }
  void set_model_id(uint16_t id) { this->model_id_ = id; }
  void set_raw_mode(bool raw) { this->raw_mode_ = raw; }

  void register_listener(Wisafe2Listener *listener) { this->listeners_.push_back(listener); }

  // Network commands. See docs/protocol.md section 3.
  void send_test(uint8_t trigger);
  void send_silence(uint8_t trigger);
  void check_pairing();
  void start_pairing();

  bool radio_ready() const { return this->radio_ready_; }
  uint32_t last_frame_ms() const { return this->last_frame_ms_; }

 protected:
  bool init_radio_();
  void write_byte_to_radio_(uint8_t byte);
  bool read_byte_from_radio_(uint8_t *out);
  bool send_command_(const uint8_t *cmd, size_t len, bool wait_for_reply);
  void handle_frame_();
  void publish_(const Event &event);

  InternalGPIOPin *ss_pin_{nullptr};
  InternalGPIOPin *sck_pin_{nullptr};
  InternalGPIOPin *sdi_pin_{nullptr};
  InternalGPIOPin *sdo_pin_{nullptr};
  InternalGPIOPin *irq_pin_{nullptr};

  uint32_t device_id_{0xA5B813};
  uint16_t model_id_{0x1103};
  bool raw_mode_{false};
  bool radio_ready_{false};
  uint32_t last_frame_ms_{0};

  FrameReader reader_;
  std::vector<Wisafe2Listener *> listeners_;
};

}  // namespace wisafe2
}  // namespace esphome
