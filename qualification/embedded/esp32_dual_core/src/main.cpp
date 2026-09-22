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
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#endif

#include <algorithm>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>

#include "nvs.h"
#include "nvs_flash.h"
#include "esp_system.h"

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
constexpr size_t COMMAND_BUF = 384;

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
    PERSIST,
    REBOOT,
    REBOOT_AFTER,
    STALL,
    TIMEOUT,
    BURST,
    SNAPSHOT,
    EXTERNAL_PROPOSAL,
    SCHED_SNAPSHOT,
    SCHED_RESET,
    SCHED_SET_ONLINE,
    SCHED_PROPOSE,
    SCHED_RECEIPT,
};

struct SchedReservationSlot {
    uint32_t reservation_id{0};
    uint32_t job_id{0};
    uint8_t target{0};
    uint16_t tokens{0};
    bool active{false};
};

struct ControlMsg {
    ControlType type{ControlType::STATUS};
    uint32_t request_id{0};
    uint64_t a{0};
    uint64_t b{0};
    FaultMode fault{FaultMode::NONE};
    char which{'P'};
    bool flag{false};
    Proposal external_proposal{};
    SchedProposal sched_proposal{};
    SchedReceiptMsg sched_receipt{};
    uint8_t sched_online_mask{0x07};
    uint16_t sched_max_inflight[3]{4, 8, 4};
    uint32_t sched_tokens{1000};
    uint8_t sched_device_id{0};
};

Program gProgram = Program::transfer_r0_to_r1();
State gAuthorityState{10, 0, 0, 0, false};
EvidenceLedger gLedger(false);
LocalClock gProposerClock{0, 3, false};
LocalClock gAuthorityClock{1000, 17, false};

SchedState gSchedState;
std::array<uint8_t, 32> gSchedEvidenceRoot{};
SchedReservationSlot gActiveReservations[128]{};

QueueHandle_t gWorkQ = nullptr;
QueueHandle_t gProposalQ = nullptr;
QueueHandle_t gControlQ = nullptr;
SemaphoreHandle_t gSerialMutex = nullptr;
TaskHandle_t gProposerTask = nullptr;
TaskHandle_t gAuthorityTask = nullptr;
uint32_t gRequestId = 1;
bool gPersistenceEnabled = false;
bool gRecoveredOnBoot = false;
uint32_t gProposerStallMs = 0;
uint32_t gProposalTimeoutMs = 5000;
uint32_t gRebootAfterCommits = 0;

constexpr uint32_t SNAPSHOT_MAGIC = 0x554f5731U;
constexpr uint32_t SNAPSHOT_VERSION = 1U;

struct PersistedSnapshot {
    uint32_t magic{SNAPSHOT_MAGIC};
    uint32_t version{SNAPSHOT_VERSION};
    uint64_t r0{0};
    uint64_t r1{0};
    uint32_t pc{0};
    uint64_t sequence{0};
    uint8_t halted{0};
    uint64_t evidence_steps{0};
    uint8_t evidence_root[32]{};
    uint64_t proposer_ticks{0};
    uint64_t authority_ticks{0};
    uint8_t checksum[32]{};
};

std::array<uint8_t, 32> snapshot_digest(const PersistedSnapshot& snap) {
    std::string body =
        std::to_string(snap.magic) + ";" +
        std::to_string(snap.version) + ";" +
        std::to_string(snap.r0) + ";" +
        std::to_string(snap.r1) + ";" +
        std::to_string(snap.pc) + ";" +
        std::to_string(snap.sequence) + ";" +
        std::to_string(static_cast<unsigned>(snap.halted)) + ";" +
        std::to_string(snap.evidence_steps) + ";";
    std::array<uint8_t, 32> root{};
    memcpy(root.data(), snap.evidence_root, root.size());
    body += hex_digest(root) + ";" +
            std::to_string(snap.proposer_ticks) + ";" +
            std::to_string(snap.authority_ticks);
    return sha256(body);
}

bool init_persistence() {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        err = nvs_flash_init();
    }
    return err == ESP_OK;
}

bool checkpoint_save() {
    if (!gPersistenceEnabled) return true;
    PersistedSnapshot snap{};
    snap.r0 = gAuthorityState.r0;
    snap.r1 = gAuthorityState.r1;
    snap.pc = gAuthorityState.pc;
    snap.sequence = gAuthorityState.sequence;
    snap.halted = gAuthorityState.halted ? 1 : 0;
    snap.evidence_steps = static_cast<uint64_t>(gLedger.size());
    const auto root = gLedger.root();
    memcpy(snap.evidence_root, root.data(), root.size());
    snap.proposer_ticks = gProposerClock.ticks;
    snap.authority_ticks = gAuthorityClock.ticks;
    const auto digest = snapshot_digest(snap);
    memcpy(snap.checksum, digest.data(), digest.size());

    nvs_handle_t handle;
    if (nvs_open("uowq", NVS_READWRITE, &handle) != ESP_OK) return false;
    const esp_err_t set_err = nvs_set_blob(handle, "snapshot", &snap, sizeof(snap));
    const esp_err_t commit_err = set_err == ESP_OK ? nvs_commit(handle) : set_err;
    nvs_close(handle);
    return set_err == ESP_OK && commit_err == ESP_OK;
}

bool checkpoint_load() {
    nvs_handle_t handle;
    if (nvs_open("uowq", NVS_READONLY, &handle) != ESP_OK) return false;
    PersistedSnapshot snap{};
    size_t len = sizeof(snap);
    const esp_err_t err = nvs_get_blob(handle, "snapshot", &snap, &len);
    nvs_close(handle);
    if (err != ESP_OK || len != sizeof(snap)) return false;
    if (snap.magic != SNAPSHOT_MAGIC || snap.version != SNAPSHOT_VERSION) return false;
    const auto expected = snapshot_digest(snap);
    if (memcmp(expected.data(), snap.checksum, expected.size()) != 0) return false;

    gAuthorityState = State{snap.r0, snap.r1, snap.pc, snap.sequence, snap.halted != 0};
    std::array<uint8_t, 32> root{};
    memcpy(root.data(), snap.evidence_root, root.size());
    gLedger.restore_checkpoint(root, static_cast<size_t>(snap.evidence_steps));
    gProposerClock.ticks = snap.proposer_ticks;
    gAuthorityClock.ticks = snap.authority_ticks;
    gPersistenceEnabled = true;
    gRecoveredOnBoot = true;
    return true;
}

void checkpoint_clear() {
    nvs_handle_t handle;
    if (nvs_open("uowq", NVS_READWRITE, &handle) == ESP_OK) {
        nvs_erase_key(handle, "snapshot");
        nvs_commit(handle);
        nvs_close(handle);
    }
}

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
    usb_serial_jtag_write_bytes(line.data(), line.size(), pdMS_TO_TICKS(5));
    usb_serial_jtag_write_bytes("\n", 1, pdMS_TO_TICKS(5));
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
    s += ",\"persistence_enabled\":" + std::string(gPersistenceEnabled ? "true" : "false");
    s += ",\"recovered_on_boot\":" + std::string(gRecoveredOnBoot ? "true" : "false");
    s += ",\"proposer_stall_ms\":" + std::to_string(gProposerStallMs);
    s += ",\"proposal_timeout_ms\":" + std::to_string(gProposalTimeoutMs);
    s += ",\"work_queue_depth\":" + std::to_string(gWorkQ ? uxQueueMessagesWaiting(gWorkQ) : 0);
    s += ",\"proposal_queue_depth\":" + std::to_string(gProposalQ ? uxQueueMessagesWaiting(gProposalQ) : 0);
    s += ",\"control_queue_depth\":" + std::to_string(gControlQ ? uxQueueMessagesWaiting(gControlQ) : 0);
    if (note) s += ",\"note\":\"" + json_escape(note) + "\"";
    s += "}";
    emit_line(s);
}

void emit_snapshot(uint32_t request_id) {
    const auto state_hash = hex_digest(hash_state(gAuthorityState));
    std::string s = "{\"event\":\"snapshot\"";
    s += ",\"request_id\":" + std::to_string(request_id);
    s += ",\"r0\":" + u64_string(gAuthorityState.r0);
    s += ",\"r1\":" + u64_string(gAuthorityState.r1);
    s += ",\"pc\":" + std::to_string(gAuthorityState.pc);
    s += ",\"sequence\":" + u64_string(gAuthorityState.sequence);
    s += ",\"halted\":" + std::string(gAuthorityState.halted ? "true" : "false");
    s += ",\"state_hash\":\"" + state_hash + "\"";
    s += ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"";
    s += "}";
    emit_line(s);
}

void emit_sched_snapshot(uint32_t request_id) {
    const auto state_hash = hex_digest(hash_sched_state(gSchedState));
    const auto root = hex_digest(gSchedEvidenceRoot);
    std::string s = "{\"event\":\"sched_snapshot\"";
    s += ",\"request_id\":" + std::to_string(request_id);
    s += ",\"epoch\":" + std::to_string(gSchedState.epoch);
    s += ",\"reservation_seq\":" + std::to_string(gSchedState.reservation_seq);
    s += ",\"completion_seq\":" + std::to_string(gSchedState.completion_seq);
    s += ",\"online_mask\":" + std::to_string(static_cast<uint32_t>(gSchedState.online_mask));
    s += ",\"inflight_cpu\":" + std::to_string(gSchedState.inflight[0]);
    s += ",\"inflight_gpu\":" + std::to_string(gSchedState.inflight[1]);
    s += ",\"inflight_npu\":" + std::to_string(gSchedState.inflight[2]);
    s += ",\"max_cpu\":" + std::to_string(gSchedState.max_inflight[0]);
    s += ",\"max_gpu\":" + std::to_string(gSchedState.max_inflight[1]);
    s += ",\"max_npu\":" + std::to_string(gSchedState.max_inflight[2]);
    s += ",\"resource_tokens\":" + std::to_string(gSchedState.resource_tokens);
    s += ",\"state_hash\":\"" + state_hash + "\"";
    s += ",\"evidence_root\":\"" + root + "\"}";
    emit_line(s);
}

void emit_decision(uint32_t request_id, const Proposal& p, const StepResult& r, const char* origin = "internal") {
    std::string s = "{\"event\":\"decision\"";
    s += ",\"request_id\":" + std::to_string(request_id);
    s += ",\"origin\":\"" + std::string(origin) + "\"";
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
        if (gProposerStallMs > 0) {
            vTaskDelay(pdMS_TO_TICKS(gProposerStallMs));
        }
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
    const TickType_t started = xTaskGetTickCount();
    const TickType_t timeout_ticks = pdMS_TO_TICKS(gProposalTimeoutMs);
    bool matched = false;
    while (!matched) {
        const TickType_t now = xTaskGetTickCount();
        const TickType_t elapsed = now - started;
        if (elapsed >= timeout_ticks) {
            emit_status("error", request_id, "proposal timeout");
            return false;
        }
        const TickType_t remaining = timeout_ticks - elapsed;
        if (xQueueReceive(gProposalQ, &pm, remaining) != pdTRUE) {
            emit_status("error", request_id, "proposal timeout");
            return false;
        }
        if (pm.request_id != request_id) {
            emit_line("{\"event\":\"discarded_proposal\",\"request_id\":" +
                      std::to_string(request_id) +
                      ",\"stale_request_id\":" + std::to_string(pm.request_id) + "}");
            continue;
        }
        matched = true;
    }

    gAuthorityClock.advance();
    const auto before_hash = hash_state(gAuthorityState);
    const auto result = commit(gProgram, gAuthorityState, pm.proposal, gLedger);
    if (result.committed) {
        gAuthorityState = result.state;
        if (gPersistenceEnabled && !checkpoint_save()) {
            emit_status("fatal", request_id, "checkpoint save failed");
            return false;
        }
    } else if (hash_state(gAuthorityState) != before_hash) {
        emit_status("fatal", request_id, "rejected proposal mutated authority state");
        return false;
    }

    emit_decision(request_id, pm.proposal, result);

    if (result.committed && gRebootAfterCommits > 0) {
        --gRebootAfterCommits;
        if (gRebootAfterCommits == 0) {
            if (gPersistenceEnabled) checkpoint_save();
            emit_status("rebooting", request_id, "scheduled reboot after commit");
            vTaskDelay(pdMS_TO_TICKS(50));
            esp_restart();
        }
    }
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
                gRecoveredOnBoot = false;
                if (gPersistenceEnabled && !checkpoint_save()) {
                    emit_status("error", c.request_id, "checkpoint save failed");
                    break;
                }
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
            case ControlType::PERSIST:
                gPersistenceEnabled = c.flag;
                if (gPersistenceEnabled) {
                    if (!checkpoint_save()) {
                        emit_status("error", c.request_id, "checkpoint save failed");
                        break;
                    }
                } else {
                    checkpoint_clear();
                    gRecoveredOnBoot = false;
                }
                emit_status("persist", c.request_id);
                break;
            case ControlType::REBOOT:
                if (gPersistenceEnabled) checkpoint_save();
                emit_status("rebooting", c.request_id, "operator requested reboot");
                vTaskDelay(pdMS_TO_TICKS(50));
                esp_restart();
                break;
            case ControlType::REBOOT_AFTER:
                gRebootAfterCommits = static_cast<uint32_t>(c.a);
                emit_status("reboot_after", c.request_id);
                break;
            case ControlType::STALL:
                gProposerStallMs = static_cast<uint32_t>(c.a);
                emit_status("stall", c.request_id);
                break;
            case ControlType::TIMEOUT:
                gProposalTimeoutMs = static_cast<uint32_t>(c.a);
                emit_status("timeout", c.request_id);
                break;
            case ControlType::SNAPSHOT:
                emit_snapshot(c.request_id);
                break;
            case ControlType::EXTERNAL_PROPOSAL: {
                gAuthorityClock.advance();
                const auto before_hash = hash_state(gAuthorityState);
                const auto result = commit(gProgram, gAuthorityState, c.external_proposal, gLedger);
                if (result.committed) {
                    gAuthorityState = result.state;
                    if (gPersistenceEnabled && !checkpoint_save()) {
                        emit_status("fatal", c.request_id, "checkpoint save failed");
                        break;
                    }
                } else if (hash_state(gAuthorityState) != before_hash) {
                    emit_status("fatal", c.request_id, "external rejection mutated authority state");
                    break;
                }
                emit_decision(c.request_id, c.external_proposal, result, "external");
                break;
            }
            case ControlType::BURST: {
                const uint32_t requested = static_cast<uint32_t>(std::min<uint64_t>(c.a, 64));
                uint32_t enqueued = 0;
                for (uint32_t i = 0; i < requested; ++i) {
                    WorkItem w{};
                    w.snapshot = gAuthorityState;
                    w.fault = FaultMode::NONE;
                    w.request_id = c.request_id;
                    if (xQueueSend(gWorkQ, &w, 0) != pdTRUE) break;
                    ++enqueued;
                }
                uint32_t committed = 0;
                uint32_t rejected = 0;
                for (uint32_t i = 0; i < enqueued; ++i) {
                    ProposalMsg pm{};
                    if (xQueueReceive(gProposalQ, &pm, pdMS_TO_TICKS(gProposalTimeoutMs)) != pdTRUE) break;
                    gAuthorityClock.advance();
                    const auto result = commit(gProgram, gAuthorityState, pm.proposal, gLedger);
                    if (result.committed) {
                        gAuthorityState = result.state;
                        ++committed;
                        if (gPersistenceEnabled) checkpoint_save();
                    } else {
                        ++rejected;
                    }
                    emit_decision(c.request_id, pm.proposal, result);
                }
                emit_line("{\"event\":\"burst_complete\",\"request_id\":" +
                          std::to_string(c.request_id) +
                          ",\"requested\":" + std::to_string(requested) +
                          ",\"enqueued\":" + std::to_string(enqueued) +
                          ",\"committed\":" + std::to_string(committed) +
                          ",\"rejected\":" + std::to_string(rejected) +
                          ",\"state_hash\":\"" + hex_digest(hash_state(gAuthorityState)) +
                          "\",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}");
                break;
            }
            case ControlType::SCHED_SNAPSHOT:
                emit_sched_snapshot(c.request_id);
                break;
            case ControlType::SCHED_RESET:
                gSchedState.epoch++;
                gSchedState.reservation_seq = 0;
                gSchedState.completion_seq = 0;
                gSchedState.online_mask = c.sched_online_mask;
                gSchedState.inflight[0] = gSchedState.inflight[1] = gSchedState.inflight[2] = 0;
                gSchedState.max_inflight[0] = c.sched_max_inflight[0];
                gSchedState.max_inflight[1] = c.sched_max_inflight[1];
                gSchedState.max_inflight[2] = c.sched_max_inflight[2];
                gSchedState.resource_tokens = c.sched_tokens;
                for (size_t i = 0; i < 128; ++i) gActiveReservations[i].active = false;
                gSchedEvidenceRoot.fill(0);
                emit_sched_snapshot(c.request_id);
                break;
            case ControlType::SCHED_SET_ONLINE: {
                const uint8_t dev = c.sched_device_id;
                if (dev < 3) {
                    if (c.flag) {
                        gSchedState.online_mask |= (1 << dev);
                    } else {
                        gSchedState.online_mask &= ~(1 << dev);
                    }
                    gSchedState.epoch++;
                }
                emit_sched_snapshot(c.request_id);
                break;
            }
            case ControlType::SCHED_PROPOSE: {
                const auto& p = c.sched_proposal;
                const auto current_hash = hash_sched_state(gSchedState);
                SchedRejectReason reason = SchedRejectReason::NONE;

                if (p.pre_state_hash != current_hash) {
                    reason = SchedRejectReason::STALE_STATE_HASH;
                } else if (p.target_device >= 3) {
                    reason = SchedRejectReason::INVALID_TARGET;
                } else if ((gSchedState.online_mask & (1 << p.target_device)) == 0) {
                    reason = SchedRejectReason::DEVICE_OFFLINE;
                } else if (gSchedState.inflight[p.target_device] >= gSchedState.max_inflight[p.target_device]) {
                    reason = SchedRejectReason::DEVICE_CAPACITY_EXCEEDED;
                } else if (gSchedState.resource_tokens < p.tokens) {
                    reason = SchedRejectReason::INSUFFICIENT_TOKENS;
                }

                if (reason == SchedRejectReason::NONE) {
                    gSchedState.inflight[p.target_device]++;
                    gSchedState.resource_tokens -= p.tokens;
                    gSchedState.reservation_seq++;
                    const uint32_t res_id = gSchedState.reservation_seq;

                    const size_t slot = res_id % 128;
                    gActiveReservations[slot].reservation_id = res_id;
                    gActiveReservations[slot].job_id = p.job_id;
                    gActiveReservations[slot].target = p.target_device;
                    gActiveReservations[slot].tokens = p.tokens;
                    gActiveReservations[slot].active = true;

                    const auto post_hash = hash_sched_state(gSchedState);

                    const auto prev_evidence_root = gSchedEvidenceRoot;
                    std::ostringstream ev;
                    ev << hex_digest(prev_evidence_root) << ":RESERVE:" << res_id << ":" << p.job_id
                       << ":" << static_cast<uint32_t>(p.target_device) << ":" << p.tokens << ":" << hex_digest(post_hash);
                    gSchedEvidenceRoot = sha256(ev.str());

                    std::string s = "{\"event\":\"sched_decision\"";
                    s += ",\"request_id\":" + std::to_string(c.request_id);
                    s += ",\"committed\":true";
                    s += ",\"reason\":\"NONE\"";
                    s += ",\"reservation_id\":" + std::to_string(res_id);
                    s += ",\"job_id\":" + std::to_string(p.job_id);
                    s += ",\"target\":" + std::to_string(p.target_device);
                    s += ",\"post_state_hash\":\"" + hex_digest(post_hash) + "\"";
                    s += ",\"prev_evidence_root\":\"" + hex_digest(prev_evidence_root) + "\"";
                    s += ",\"evidence_root\":\"" + hex_digest(gSchedEvidenceRoot) + "\"}";
                    emit_line(s);
                } else {
                    std::string s = "{\"event\":\"sched_decision\"";
                    s += ",\"request_id\":" + std::to_string(c.request_id);
                    s += ",\"committed\":false";
                    s += ",\"reason\":\"" + std::string(sched_reject_reason_string(reason)) + "\"";
                    s += ",\"reservation_id\":0";
                    s += ",\"job_id\":" + std::to_string(p.job_id);
                    s += ",\"target\":" + std::to_string(p.target_device);
                    s += ",\"post_state_hash\":\"" + hex_digest(current_hash) + "\"";
                    s += ",\"evidence_root\":\"" + hex_digest(gSchedEvidenceRoot) + "\"}";
                    emit_line(s);
                }
                break;
            }
            case ControlType::SCHED_RECEIPT: {
                const auto& r = c.sched_receipt;
                const size_t slot = r.reservation_id % 128;
                SchedRejectReason reason = SchedRejectReason::NONE;

                if (r.reservation_id == 0 || r.reservation_id > gSchedState.reservation_seq ||
                    !gActiveReservations[slot].active ||
                    gActiveReservations[slot].reservation_id != r.reservation_id) {
                    reason = SchedRejectReason::INVALID_RESERVATION;
                }

                if (reason == SchedRejectReason::NONE) {
                    const uint8_t target = gActiveReservations[slot].target;
                    const uint16_t tokens = gActiveReservations[slot].tokens;
                    if (gSchedState.inflight[target] > 0) gSchedState.inflight[target]--;
                    gSchedState.resource_tokens += tokens;
                    gSchedState.completion_seq++;
                    gActiveReservations[slot].active = false;

                    const auto post_hash = hash_sched_state(gSchedState);

                    const auto prev_evidence_root = gSchedEvidenceRoot;
                    std::ostringstream ev;
                    ev << hex_digest(prev_evidence_root) << ":RECEIPT:" << r.reservation_id << ":"
                       << static_cast<uint32_t>(r.status) << ":" << r.latency_us << ":"
                       << hex_digest(r.output_digest) << ":" << hex_digest(post_hash);
                    gSchedEvidenceRoot = sha256(ev.str());

                    std::string s = "{\"event\":\"sched_receipt\"";
                    s += ",\"request_id\":" + std::to_string(c.request_id);
                    s += ",\"committed\":true";
                    s += ",\"reason\":\"NONE\"";
                    s += ",\"reservation_id\":" + std::to_string(r.reservation_id);
                    s += ",\"completion_seq\":" + std::to_string(gSchedState.completion_seq);
                    s += ",\"latency_us\":" + std::to_string(r.latency_us);
                    s += ",\"post_state_hash\":\"" + hex_digest(post_hash) + "\"";
                    s += ",\"prev_evidence_root\":\"" + hex_digest(prev_evidence_root) + "\"";
                    s += ",\"evidence_root\":\"" + hex_digest(gSchedEvidenceRoot) + "\"}";
                    emit_line(s);
                } else {
                    const auto current_hash = hash_sched_state(gSchedState);
                    std::string s = "{\"event\":\"sched_receipt\"";
                    s += ",\"request_id\":" + std::to_string(c.request_id);
                    s += ",\"committed\":false";
                    s += ",\"reason\":\"" + std::string(sched_reject_reason_string(reason)) + "\"";
                    s += ",\"reservation_id\":" + std::to_string(r.reservation_id);
                    s += ",\"completion_seq\":" + std::to_string(gSchedState.completion_seq);
                    s += ",\"latency_us\":0";
                    s += ",\"post_state_hash\":\"" + hex_digest(current_hash) + "\"";
                    s += ",\"evidence_root\":\"" + hex_digest(gSchedEvidenceRoot) + "\"}";
                    emit_line(s);
                }
                break;
            }
        }
    }
}

void print_help() {
    emit_line("{\"event\":\"help\",\"commands\":[\"HELP\",\"STATUS\",\"SNAPSHOT\",\"RESET <r0> <r1>\",\"STEP [NONE|TAMPER_STATE|TAMPER_PREHASH|TAMPER_ROUTE]\",\"RUN <budget> [fault]\",\"EXT_PROPOSE <prehash> <r0> <r1> <pc> <sequence> <halted> <selected_pc> <proposal_hash>\",\"CLOCKS <proposal_stride> <authority_stride>\",\"FREEZE <P|A> <0|1>\",\"PERSIST <0|1>\",\"REBOOT\",\"REBOOT_AFTER <commits>\",\"STALL <ms>\",\"TIMEOUT <ms>\",\"BURST <count>\",\"SCHED_SNAPSHOT\",\"SCHED_RESET <online_mask> <max_cpu> <max_gpu> <max_npu> <tokens>\",\"SCHED_SET_ONLINE <dev> <0|1>\",\"SCHED_PROPOSE <prehash> <job_id> <target> <tokens> <proposal_hash>\",\"SCHED_RECEIPT <reservation_id> <status> <latency_us> <digest>\"]}");
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
    while (parts.size() < 16 && start < line.size()) {
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
    } else if (parts[0] == "SNAPSHOT") {
        c.type = ControlType::SNAPSHOT;
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
    } else if (parts[0] == "EXT_PROPOSE" && parts.size() >= 9) {
        c.type = ControlType::EXTERNAL_PROPOSAL;
        Proposal p{};
        uint64_t r0 = 0, r1 = 0, pc = 0, sequence = 0, halted = 0, selected_pc = 0;
        if (!parse_hex_digest(parts[1], p.pre_state_hash)
            || !parse_u64(parts[2], r0)
            || !parse_u64(parts[3], r1)
            || !parse_u64(parts[4], pc)
            || !parse_u64(parts[5], sequence)
            || !parse_u64(parts[6], halted)
            || !parse_u64(parts[7], selected_pc)
            || !parse_hex_digest(parts[8], p.proposal_hash)
            || halted > 1
            || pc > UINT32_MAX
            || selected_pc > UINT32_MAX) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad EXT_PROPOSE envelope\"}"); return;
        }
        p.proposed = State{r0, r1, static_cast<uint32_t>(pc), sequence, halted != 0};
        p.selected_pc = static_cast<uint32_t>(selected_pc);
        p.halted = halted != 0;
        p.proposer_clock = 0;
        c.external_proposal = p;
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
    } else if (parts[0] == "PERSIST" && parts.size() >= 2) {
        c.type = ControlType::PERSIST;
        c.flag = parts[1] == "1";
    } else if (parts[0] == "REBOOT") {
        c.type = ControlType::REBOOT;
    } else if (parts[0] == "REBOOT_AFTER" && parts.size() >= 2) {
        c.type = ControlType::REBOOT_AFTER;
        if (!parse_u64(parts[1], c.a)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad REBOOT_AFTER argument\"}"); return;
        }
    } else if (parts[0] == "STALL" && parts.size() >= 2) {
        c.type = ControlType::STALL;
        if (!parse_u64(parts[1], c.a)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad STALL argument\"}"); return;
        }
    } else if (parts[0] == "TIMEOUT" && parts.size() >= 2) {
        c.type = ControlType::TIMEOUT;
        if (!parse_u64(parts[1], c.a) || c.a == 0) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad TIMEOUT argument\"}"); return;
        }
    } else if (parts[0] == "BURST" && parts.size() >= 2) {
        c.type = ControlType::BURST;
        if (!parse_u64(parts[1], c.a) || c.a == 0) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad BURST argument\"}"); return;
        }
    } else if (parts[0] == "SCHED_SNAPSHOT" || parts[0] == "SCHED_STATUS") {
        c.type = ControlType::SCHED_SNAPSHOT;
    } else if (parts[0] == "SCHED_RESET" && parts.size() >= 6) {
        c.type = ControlType::SCHED_RESET;
        uint64_t mask = 7, mc = 4, mg = 8, mn = 4, tokens = 1000;
        if (!parse_u64(parts[1], mask) || !parse_u64(parts[2], mc) ||
            !parse_u64(parts[3], mg) || !parse_u64(parts[4], mn) ||
            !parse_u64(parts[5], tokens)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad SCHED_RESET arguments\"}"); return;
        }
        c.sched_online_mask = static_cast<uint8_t>(mask);
        c.sched_max_inflight[0] = static_cast<uint16_t>(mc);
        c.sched_max_inflight[1] = static_cast<uint16_t>(mg);
        c.sched_max_inflight[2] = static_cast<uint16_t>(mn);
        c.sched_tokens = static_cast<uint32_t>(tokens);
    } else if (parts[0] == "SCHED_SET_ONLINE" && parts.size() >= 3) {
        c.type = ControlType::SCHED_SET_ONLINE;
        uint64_t dev = 0, online = 0;
        if (!parse_u64(parts[1], dev) || !parse_u64(parts[2], online)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad SCHED_SET_ONLINE arguments\"}"); return;
        }
        c.sched_device_id = static_cast<uint8_t>(dev);
        c.flag = (online != 0);
    } else if (parts[0] == "SCHED_PROPOSE" && parts.size() >= 6) {
        c.type = ControlType::SCHED_PROPOSE;
        SchedProposal p{};
        uint64_t job_id = 0, target = 0, tokens = 1;
        if (!parse_hex_digest(parts[1], p.pre_state_hash)
            || !parse_u64(parts[2], job_id)
            || !parse_u64(parts[3], target)
            || !parse_u64(parts[4], tokens)
            || !parse_hex_digest(parts[5], p.proposal_hash)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad SCHED_PROPOSE arguments\"}"); return;
        }
        p.job_id = static_cast<uint32_t>(job_id);
        p.target_device = static_cast<uint8_t>(target);
        p.tokens = static_cast<uint16_t>(tokens);
        c.sched_proposal = p;
    } else if (parts[0] == "SCHED_RECEIPT" && parts.size() >= 5) {
        c.type = ControlType::SCHED_RECEIPT;
        SchedReceiptMsg r{};
        uint64_t res_id = 0, status = 0, latency_us = 0;
        if (!parse_u64(parts[1], res_id)
            || !parse_u64(parts[2], status)
            || !parse_u64(parts[3], latency_us)
            || !parse_hex_digest(parts[4], r.output_digest)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad SCHED_RECEIPT arguments\"}"); return;
        }
        r.reservation_id = static_cast<uint32_t>(res_id);
        r.status = static_cast<uint8_t>(status);
        r.latency_us = static_cast<uint32_t>(latency_us);
        c.sched_receipt = r;
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
    SET_PERI_REG_MASK(RTC_CNTL_USB_CONF_REG, RTC_CNTL_USB_RESET_DISABLE);
    vTaskDelay(pdMS_TO_TICKS(750));
#endif

    init_persistence();
    checkpoint_load();

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
