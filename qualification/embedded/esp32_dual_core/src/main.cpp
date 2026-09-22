#include <Arduino.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

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

String u64_string(uint64_t value) {
    char buf[24];
    snprintf(buf, sizeof(buf), "%" PRIu64, value);
    return String(buf);
}

String json_escape(const String& s) {
    String out;
    for (size_t i = 0; i < s.length(); ++i) {
        const char c = s[i];
        if (c == '\\' || c == '"') out += '\\';
        out += c;
    }
    return out;
}

void emit_line(const String& line) {
    if (gSerialMutex) xSemaphoreTake(gSerialMutex, portMAX_DELAY);
    Serial.println(line);
    if (gSerialMutex) xSemaphoreGive(gSerialMutex);
}

void emit_status(const char* event, uint32_t request_id, const char* note = nullptr) {
    const auto state_hash = hex_digest(hash_state(gAuthorityState));
    const auto root = hex_digest(gLedger.root());
    String s = "{\"event\":\"" + String(event) + "\"";
    s += ",\"request_id\":" + String(request_id);
    s += ",\"proposer_core\":" + String(UOW_PROPOSER_CORE);
    s += ",\"authority_core\":" + String(UOW_AUTHORITY_CORE);
    s += ",\"r0\":" + u64_string(gAuthorityState.r0);
    s += ",\"r1\":" + u64_string(gAuthorityState.r1);
    s += ",\"pc\":" + String(gAuthorityState.pc);
    s += ",\"sequence\":" + u64_string(gAuthorityState.sequence);
    s += ",\"halted\":" + String(gAuthorityState.halted ? "true" : "false");
    s += ",\"state_hash\":\"" + String(state_hash.c_str()) + "\"";
    s += ",\"evidence_root\":\"" + String(root.c_str()) + "\"";
    s += ",\"evidence_steps\":" + u64_string(static_cast<uint64_t>(gLedger.size()));
    s += ",\"proposal_clock\":" + u64_string(gProposerClock.read());
    s += ",\"authority_clock\":" + u64_string(gAuthorityClock.read());
    if (note) s += ",\"note\":\"" + json_escape(String(note)) + "\"";
    s += "}";
    emit_line(s);
}

void emit_decision(uint32_t request_id, const Proposal& p, const StepResult& r) {
    String s = "{\"event\":\"decision\"";
    s += ",\"request_id\":" + String(request_id);
    s += ",\"committed\":" + String(r.committed ? "true" : "false");
    s += ",\"reason\":\"" + String(reject_reason_string(r.certificate.reason)) + "\"";
    s += ",\"proposal_hash\":\"" + String(hex_digest(p.proposal_hash).c_str()) + "\"";
    s += ",\"certificate_hash\":\"" + String(hex_digest(r.certificate.certificate_hash).c_str()) + "\"";
    s += ",\"post_state_hash\":\"" + String(hex_digest(hash_state(r.state)).c_str()) + "\"";
    s += ",\"evidence_root\":\"" + String(hex_digest(gLedger.root()).c_str()) + "\"";
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

bool parse_u64(const String& s, uint64_t& out) {
    if (!s.length()) return false;
    char* end = nullptr;
    out = strtoull(s.c_str(), &end, 10);
    return end && *end == '\0';
}

void handle_command(String line) {
    line.trim();
    if (!line.length()) return;

    String parts[4];
    int count = 0;
    int start = 0;
    while (count < 4 && start < (int)line.length()) {
        int space = line.indexOf(' ', start);
        if (space < 0) space = line.length();
        parts[count++] = line.substring(start, space);
        start = space + 1;
        while (start < (int)line.length() && line[start] == ' ') ++start;
    }
    parts[0].toUpperCase();

    if (parts[0] == "HELP") { print_help(); return; }

    ControlMsg c{};
    c.request_id = gRequestId++;

    if (parts[0] == "STATUS") {
        c.type = ControlType::STATUS;
    } else if (parts[0] == "RESET" && count >= 3) {
        c.type = ControlType::RESET;
        if (!parse_u64(parts[1], c.a) || !parse_u64(parts[2], c.b)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad RESET arguments\"}"); return;
        }
    } else if (parts[0] == "STEP") {
        c.type = ControlType::STEP;
        if (count >= 2) c.fault = parse_fault_mode(std::string(parts[1].c_str()));
    } else if (parts[0] == "RUN" && count >= 2) {
        c.type = ControlType::RUN;
        if (!parse_u64(parts[1], c.a)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad RUN budget\"}"); return;
        }
        if (count >= 3) c.fault = parse_fault_mode(std::string(parts[2].c_str()));
    } else if (parts[0] == "CLOCKS" && count >= 3) {
        c.type = ControlType::CLOCKS;
        if (!parse_u64(parts[1], c.a) || !parse_u64(parts[2], c.b)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad CLOCKS arguments\"}"); return;
        }
    } else if (parts[0] == "FREEZE" && count >= 3) {
        c.type = ControlType::FREEZE;
        parts[1].toUpperCase();
        if (parts[1] != "P" && parts[1] != "A") {
            emit_line("{\"event\":\"error\",\"reason\":\"FREEZE target must be P or A\"}"); return;
        }
        c.which = parts[1][0];
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
    Serial.begin(SERIAL_BAUD);
    delay(750);

    gSerialMutex = xSemaphoreCreateMutex();
    gWorkQ = xQueueCreate(4, sizeof(WorkItem));
    gProposalQ = xQueueCreate(4, sizeof(ProposalMsg));
    gControlQ = xQueueCreate(8, sizeof(ControlMsg));

    if (!gSerialMutex || !gWorkQ || !gProposalQ || !gControlQ) {
        Serial.println("{\"event\":\"fatal\",\"reason\":\"FreeRTOS allocation failed\"}");
        for (;;) delay(1000);
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
    while (Serial.available()) {
        const char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            buf[pos] = '\0';
            handle_command(String(buf));
            pos = 0;
        } else if (pos + 1 < sizeof(buf)) {
            buf[pos++] = c;
        } else {
            pos = 0;
            emit_line("{\"event\":\"error\",\"reason\":\"command too long\"}");
        }
    }
    delay(2);
}
