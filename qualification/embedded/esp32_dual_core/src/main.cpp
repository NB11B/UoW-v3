#ifdef ARDUINO
#include <Arduino.h>
#else
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/usb_serial_jtag.h"
#include "esp_system.h"
#include "esp_log.h"
#endif

#include "uow_embedded.hpp"

using namespace uow_embedded;

#ifndef UOW_PROPOSER_CORE
#define UOW_PROPOSER_CORE 0
#endif
#ifndef UOW_AUTHORITY_CORE
#define UOW_AUTHORITY_CORE 1
#endif

namespace {

constexpr uint32_t SERIAL_BAUD = 115200;
constexpr size_t COMMAND_BUF = 160;

struct WorkItem {
    State snapshot{};
    FaultMode fault{FaultMode::NONE};
    uint32_t request_id{0};
};

struct ProposalMsg {
    Proposal proposal{};
    uint32_t request_id{0};
};

enum class ControlType : uint8_t {
    STATUS,
    RESET,
    STEP,
    RUN,
    CLOCKS,
    FREEZE,
};

struct ControlMsg {
    ControlType type{ControlType::STATUS};
    uint32_t request_id{0};
    uint64_t a{0};
    uint64_t b{0};
    FaultMode fault{FaultMode::NONE};
    char which{'P'};
    bool flag{false};
};

Program gProgram = Program::transfer_r0_to_r1();
State gAuthorityState{10, 0, 0, 0, false};
EvidenceLedger gLedger(false);
LocalClock gProposerClock{0, 3, false};
LocalClock gAuthorityClock{1000, 17, false};

QueueHandle_t gWorkQ = nullptr;
QueueHandle_t gProposalQ = nullptr;
QueueHandle_t gControlQ = nullptr;
SemaphoreHandle_t gSerialMutex = nullptr;
TaskHandle_t gProposerTask = nullptr;
TaskHandle_t gAuthorityTask = nullptr;
uint32_t gRequestId = 1;

std::string u64_string(uint64_t value) {
    char buf[24];
    snprintf(buf, sizeof(buf), "%" PRIu64, value);
    return std::string(buf);
}

std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '\\' || c == '"') out += '\\';
        out += c;
    }
    return out;
}

void emit_line(const std::string& line) {
    if (gSerialMutex) xSemaphoreTake(gSerialMutex, portMAX_DELAY);
#ifdef ARDUINO
    Serial.println(line.c_str());
#else
    usb_serial_jtag_write_bytes(line.data(), line.size(), portMAX_DELAY);
    usb_serial_jtag_write_bytes("\n", 1, portMAX_DELAY);
#endif
    if (gSerialMutex) xSemaphoreGive(gSerialMutex);
}

void emit_status(const char* event, uint32_t request_id, const char* note = nullptr) {
    const auto state_hash = hex_digest(hash_state(gAuthorityState));
    const auto root = hex_digest(gLedger.root());
    std::string s = "{\"event\":\"" + std::string(event) + "\"";
    s += ",\"request_id\":" + std::to_string(request_id);
    s += ",\"proposer_core\":" + std::to_string(UOW_PROPOSER_CORE);
    s += ",\"authority_core\":" + std::to_string(UOW_AUTHORITY_CORE);
    s += ",\"r0\":" + u64_string(gAuthorityState.r0);
    s += ",\"r1\":" + u64_string(gAuthorityState.r1);
    s += ",\"pc\":" + std::to_string(gAuthorityState.pc);
    s += ",\"sequence\":" + u64_string(gAuthorityState.sequence);
    s += ",\"halted\":" + std::string(gAuthorityState.halted ? "true" : "false");
    s += ",\"state_hash\":\"" + state_hash + "\"";
    s += ",\"evidence_root\":\"" + root + "\"";
    s += ",\"evidence_steps\":" + u64_string(static_cast<uint64_t>(gLedger.size()));
    s += ",\"proposal_clock\":" + u64_string(gProposerClock.read());
    s += ",\"authority_clock\":" + u64_string(gAuthorityClock.read());
    if (note) s += ",\"note\":\"" + json_escape(note) + "\"";
    s += "}";
    emit_line(s);
}

void emit_decision(uint32_t request_id, const Proposal& p, const StepResult& r) {
    std::string s = "{\"event\":\"decision\"";
    s += ",\"request_id\":" + std::to_string(request_id);
    s += ",\"committed\":" + std::string(r.committed ? "true" : "false");
    s += ",\"reason\":\"" + std::string(reject_reason_string(r.certificate.reason)) + "\"";
    s += ",\"proposal_hash\":\"" + hex_digest(p.proposal_hash) + "\"";
    s += ",\"certificate_hash\":\"" + hex_digest(r.certificate.certificate_hash) + "\"";
    s += ",\"post_state_hash\":\"" + hex_digest(hash_state(r.state)) + "\"";
    s += ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"";
    s += ",\"proposal_clock\":" + u64_string(p.proposer_clock);
    s += ",\"authority_clock\":" + u64_string(gAuthorityClock.read());
    s += "}";
    emit_line(s);
}

void proposer_task(void*) {
    WorkItem w{};
    for (;;) {
        if (xQueueReceive(gWorkQ, &w, portMAX_DELAY) != pdTRUE) continue;
        gProposerClock.advance();
        ProposalMsg msg{};
        msg.request_id = w.request_id;
        msg.proposal = propose(gProgram, w.snapshot, gProposerClock, w.fault);
        xQueueSend(gProposalQ, &msg, portMAX_DELAY);
    }
}

bool authority_step(uint32_t request_id, FaultMode fault) {
    if (gAuthorityState.halted) {
        emit_status("halted", request_id, "no step committed; state already halted");
        return false;
    }

    WorkItem w{};
    w.snapshot = gAuthorityState;
    w.fault = fault;
    w.request_id = request_id;
    xQueueSend(gWorkQ, &w, portMAX_DELAY);

    ProposalMsg pm{};
    if (xQueueReceive(gProposalQ, &pm, pdMS_TO_TICKS(5000)) != pdTRUE) {
        emit_status("error", request_id, "proposal timeout");
        return false;
    }

    gAuthorityClock.advance();
    const auto before_hash = hash_state(gAuthorityState);
    const auto result = commit(gProgram, gAuthorityState, pm.proposal, gLedger);
    if (result.committed) {
        gAuthorityState = result.state;
    } else if (hash_state(gAuthorityState) != before_hash) {
        emit_status("fatal", request_id, "rejected proposal mutated authority state");
        return false;
    }

    emit_decision(request_id, pm.proposal, result);
    return result.committed;
}

void authority_task(void*) {
    ControlMsg c{};
    for (;;) {
        if (xQueueReceive(gControlQ, &c, portMAX_DELAY) != pdTRUE) continue;
        switch (c.type) {
            case ControlType::STATUS:
                emit_status("status", c.request_id);
                break;
            case ControlType::RESET:
                gAuthorityState = State{c.a, c.b, 0, 0, false};
                gLedger = EvidenceLedger(false);
                emit_status("reset", c.request_id);
                break;
            case ControlType::STEP:
                authority_step(c.request_id, c.fault);
                break;
            case ControlType::RUN: {
                const uint64_t budget = c.a;
                uint64_t attempted = 0;
                while (!gAuthorityState.halted && attempted < budget) {
                    if (!authority_step(c.request_id, c.fault)) break;
                    ++attempted;
                    c.fault = FaultMode::NONE;
                    taskYIELD();
                }
                emit_status("run_complete", c.request_id,
                            gAuthorityState.halted ? "HALTED" : "BUDGET_OR_REJECTION");
                break;
            }
            case ControlType::CLOCKS:
                gProposerClock.stride = c.a;
                gAuthorityClock.stride = c.b;
                emit_status("clocks", c.request_id);
                break;
            case ControlType::FREEZE:
                if (c.which == 'P') gProposerClock.frozen = c.flag;
                else if (c.which == 'A') gAuthorityClock.frozen = c.flag;
                emit_status("freeze", c.request_id);
                break;
        }
    }
}

void print_help() {
    emit_line("{\"event\":\"help\",\"commands\":[\"HELP\",\"STATUS\",\"RESET <r0> <r1>\",\"STEP [NONE|TAMPER_STATE|TAMPER_PREHASH|TAMPER_ROUTE]\",\"RUN <budget> [fault]\",\"CLOCKS <proposal_stride> <authority_stride>\",\"FREEZE <P|A> <0|1>\"]}");
}

bool parse_u64(const std::string& s, uint64_t& out) {
    if (s.empty()) return false;
    char* end = nullptr;
    out = strtoull(s.c_str(), &end, 10);
    return end && *end == '\0';
}

void handle_command(std::string line) {
    while (!line.empty() && (line.front() == ' ' || line.front() == '\t' || line.front() == '\r' || line.front() == '\n')) line.erase(0, 1);
    while (!line.empty() && (line.back() == ' ' || line.back() == '\t' || line.back() == '\r' || line.back() == '\n')) line.pop_back();
    if (line.empty()) return;

    std::vector<std::string> parts;
    size_t start = 0;
    while (parts.size() < 4 && start < line.size()) {
        while (start < line.size() && line[start] == ' ') ++start;
        if (start >= line.size()) break;
        size_t space = line.find(' ', start);
        if (space == std::string::npos) space = line.size();
        parts.push_back(line.substr(start, space - start));
        start = space;
    }
    if (parts.empty()) return;
    for (char& ch : parts[0]) ch = (char)toupper((unsigned char)ch);

    if (parts[0] == "HELP") { print_help(); return; }

    ControlMsg c{};
    c.request_id = gRequestId++;

    if (parts[0] == "STATUS") {
        c.type = ControlType::STATUS;
    } else if (parts[0] == "RESET" && parts.size() >= 3) {
        c.type = ControlType::RESET;
        if (!parse_u64(parts[1], c.a) || !parse_u64(parts[2], c.b)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad RESET arguments\"}"); return;
        }
    } else if (parts[0] == "STEP") {
        c.type = ControlType::STEP;
        if (parts.size() >= 2) c.fault = parse_fault_mode(parts[1]);
    } else if (parts[0] == "RUN" && parts.size() >= 2) {
        c.type = ControlType::RUN;
        if (!parse_u64(parts[1], c.a)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad RUN budget\"}"); return;
        }
        if (parts.size() >= 3) c.fault = parse_fault_mode(parts[2]);
    } else if (parts[0] == "CLOCKS" && parts.size() >= 3) {
        c.type = ControlType::CLOCKS;
        if (!parse_u64(parts[1], c.a) || !parse_u64(parts[2], c.b)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad CLOCKS arguments\"}"); return;
        }
    } else if (parts[0] == "FREEZE" && parts.size() >= 3) {
        c.type = ControlType::FREEZE;
        std::string target = parts[1];
        for (char& ch : target) ch = (char)toupper((unsigned char)ch);
        if (target != "P" && target != "A") {
            emit_line("{\"event\":\"error\",\"reason\":\"FREEZE target must be P or A\"}"); return;
        }
        c.which = target[0];
        c.flag = parts[2] == "1";
    } else {
        emit_line("{\"event\":\"error\",\"reason\":\"unknown command; send HELP\"}");
        return;
    }

    if (xQueueSend(gControlQ, &c, pdMS_TO_TICKS(1000)) != pdTRUE) {
        emit_line("{\"event\":\"error\",\"reason\":\"control queue full\"}");
    }
}

} // namespace

void setup() {
#ifdef ARDUINO
    Serial.begin(SERIAL_BAUD);
    delay(750);
#else
    esp_log_level_set("*", ESP_LOG_NONE);
    usb_serial_jtag_driver_config_t d_cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    d_cfg.rx_buffer_size = 4096;
    d_cfg.tx_buffer_size = 4096;
    usb_serial_jtag_driver_install(&d_cfg);
    vTaskDelay(pdMS_TO_TICKS(750));
#endif

    gSerialMutex = xSemaphoreCreateMutex();
    gWorkQ = xQueueCreate(4, sizeof(WorkItem));
    gProposalQ = xQueueCreate(4, sizeof(ProposalMsg));
    gControlQ = xQueueCreate(8, sizeof(ControlMsg));

    if (!gSerialMutex || !gWorkQ || !gProposalQ || !gControlQ) {
        emit_line("{\"event\":\"fatal\",\"reason\":\"FreeRTOS allocation failed\"}");
        for (;;) {
#ifdef ARDUINO
            delay(1000);
#else
            vTaskDelay(pdMS_TO_TICKS(1000));
#endif
        }
    }

    xTaskCreatePinnedToCore(
        proposer_task, "uow-proposer", 8192, nullptr, 2, &gProposerTask, UOW_PROPOSER_CORE);
    xTaskCreatePinnedToCore(
        authority_task, "uow-authority", 12288, nullptr, 3, &gAuthorityTask, UOW_AUTHORITY_CORE);

    emit_line("{\"event\":\"boot\",\"architecture\":\"proposal->certify->commit\",\"evidence_mode\":\"root-only-bounded-memory\"}");
    print_help();
    ControlMsg c{}; c.type = ControlType::STATUS; c.request_id = gRequestId++;
    xQueueSend(gControlQ, &c, portMAX_DELAY);
}

void loop() {
    static char buf[COMMAND_BUF];
    static size_t pos = 0;
#ifdef ARDUINO
    while (Serial.available()) {
        const char c = (char)Serial.read();
#else
    char c = 0;
    while (usb_serial_jtag_read_bytes(&c, 1, 0) > 0) {
#endif
        if (c == '\r') continue;
        if (c == '\n') {
            buf[pos] = '\0';
            handle_command(std::string(buf));
            pos = 0;
        } else if (pos + 1 < sizeof(buf)) {
            buf[pos++] = c;
        } else {
            pos = 0;
            emit_line("{\"event\":\"error\",\"reason\":\"command too long\"}");
        }
    }
#ifdef ARDUINO
    delay(2);
#else
    vTaskDelay(pdMS_TO_TICKS(2));
#endif
}

#ifndef ARDUINO
extern "C" void app_main(void) {
    setup();
    for (;;) {
        loop();
    }
}
#endif
