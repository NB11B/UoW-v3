#pragma once

#include <array>
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

namespace uow_embedded {

enum class Op : uint8_t { INC = 0, DECJZ = 1, HALT = 2 };
enum class FaultMode : uint8_t {
    NONE = 0,
    TAMPER_STATE = 1,
    TAMPER_PREHASH = 2,
    TAMPER_ROUTE = 3,
};

enum class RejectReason : uint8_t {
    NONE = 0,
    STALE_PRE_STATE = 1,
    STATE_DIVERGENCE = 2,
    ROUTE_DIVERGENCE = 3,
    HALT_DIVERGENCE = 4,
    PROPOSAL_HASH_DIVERGENCE = 5,
};

struct Instruction {
    Op op{Op::HALT};
    uint8_t reg{0};
    uint32_t a{0};
    uint32_t b{0};
};

struct State {
    uint64_t r0{0};
    uint64_t r1{0};
    uint32_t pc{0};
    uint64_t sequence{0};
    bool halted{false};
};

struct LocalClock {
    uint64_t ticks{0};
    uint64_t stride{1};
    bool frozen{false};

    uint64_t read() const { return ticks; }
    void advance();
};

struct Proposal {
    std::array<uint8_t, 32> pre_state_hash{};
    std::array<uint8_t, 32> proposal_hash{};
    State proposed{};
    uint32_t selected_pc{0};
    bool halted{false};
    uint64_t proposer_clock{0}; // observational only; never authority-bearing
};

struct Certificate {
    bool valid{false};
    RejectReason reason{RejectReason::NONE};
    std::array<uint8_t, 32> certificate_hash{};
};

struct EvidenceRecord {
    uint64_t step{0};
    std::array<uint8_t, 32> pre_state_hash{};
    std::array<uint8_t, 32> post_state_hash{};
    std::array<uint8_t, 32> proposal_hash{};
    std::array<uint8_t, 32> certificate_hash{};
    std::array<uint8_t, 32> prev_record_hash{};
    std::array<uint8_t, 32> record_hash{};
};

struct StepResult {
    bool committed{false};
    Certificate certificate{};
    EvidenceRecord evidence{};
    State state{};
};

class Program {
public:
    Program() = default;
    explicit Program(std::vector<Instruction> code) : code_(std::move(code)) {}

    const Instruction& at(uint32_t pc) const;
    size_t size() const { return code_.size(); }
    static Program transfer_r0_to_r1();

private:
    std::vector<Instruction> code_{};
};

class EvidenceLedger {
public:
    explicit EvidenceLedger(bool retain_records = true) : retain_records_(retain_records) {}
    bool append(const EvidenceRecord& record);
    bool verify() const;
    const std::array<uint8_t, 32>& root() const;
    void restore_checkpoint(const std::array<uint8_t, 32>& root, size_t size);
    size_t size() const { return size_; }
    const std::vector<EvidenceRecord>& records() const { return records_; }

private:
    bool retain_records_{true};
    bool valid_{true};
    size_t size_{0};
    std::vector<EvidenceRecord> records_{};
    std::array<uint8_t, 32> root_{};
};

std::array<uint8_t, 32> sha256(const uint8_t* data, size_t len);
std::array<uint8_t, 32> sha256(const std::string& text);
std::string hex_digest(const std::array<uint8_t, 32>& d);
bool parse_hex_digest(const std::string& text, std::array<uint8_t, 32>& out);

std::array<uint8_t, 32> hash_state(const State& s);
std::array<uint8_t, 32> hash_proposal_body(const Proposal& p);
std::array<uint8_t, 32> hash_certificate_body(
    const Proposal& p,
    bool valid,
    RejectReason reason);
std::array<uint8_t, 32> hash_evidence_body(const EvidenceRecord& r);

Proposal propose(
    const Program& program,
    const State& authoritative_snapshot,
    const LocalClock& proposer_clock,
    FaultMode fault = FaultMode::NONE);

Certificate certify(
    const Program& program,
    const State& authoritative_state,
    const Proposal& proposal);

StepResult commit(
    const Program& program,
    const State& authoritative_state,
    const Proposal& proposal,
    EvidenceLedger& ledger);

StepResult execute_one(
    const Program& program,
    const State& authoritative_state,
    LocalClock& proposer_clock,
    LocalClock& authority_clock,
    EvidenceLedger& ledger,
    FaultMode fault = FaultMode::NONE);

const char* reject_reason_string(RejectReason reason);
const char* fault_mode_string(FaultMode mode);
FaultMode parse_fault_mode(const std::string& text);

// -----------------------------------------------------------------------------
// Heterogeneous Workload Scheduling Authority
// -----------------------------------------------------------------------------
enum class SchedRejectReason : uint8_t {
    NONE = 0,
    STALE_STATE_HASH = 1,
    INVALID_TARGET = 2,
    DEVICE_OFFLINE = 3,
    DEVICE_CAPACITY_EXCEEDED = 4,
    INSUFFICIENT_TOKENS = 5,
    INVALID_RESERVATION = 6,
    ALREADY_COMPLETED = 7,
    PROPOSAL_HASH_MISMATCH = 8,
};

struct SchedState {
    uint32_t epoch{0};
    uint32_t reservation_seq{0};
    uint32_t completion_seq{0};
    uint8_t online_mask{0x07}; // bit 0: CPU, bit 1: GPU, bit 2: NPU
    uint16_t inflight[3]{0, 0, 0};
    uint16_t max_inflight[3]{4, 8, 4};
    uint32_t resource_tokens{1000};
};

struct SchedProposal {
    std::array<uint8_t, 32> pre_state_hash{};
    std::array<uint8_t, 32> proposal_hash{};
    uint32_t job_id{0};
    uint8_t target_device{0};
    uint16_t tokens{1};
};

struct SchedReceiptMsg {
    uint32_t reservation_id{0};
    uint8_t status{0};
    uint32_t latency_us{0};
    std::array<uint8_t, 32> output_digest{};
};

std::string sched_canonical_state(const SchedState& s);
std::array<uint8_t, 32> hash_sched_state(const SchedState& s);
const char* sched_reject_reason_string(SchedRejectReason reason);

} // namespace uow_embedded
