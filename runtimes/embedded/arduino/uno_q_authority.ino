#include <Arduino.h>
#include <Arduino_RouterBridge.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "uow_embedded.hpp"

using namespace uow_embedded;

namespace {

const std::string NODE_ID = "authority_b_unoq_stm32";
const std::string RULESET_VERSION = "uow-authority-v1";

enum class NodeMode : uint8_t {
    ACTIVE = 0,
    STALE = 1,
    QUARANTINED = 2
};

const char* mode_string(NodeMode m) {
    switch (m) {
        case NodeMode::ACTIVE: return "ACTIVE";
        case NodeMode::STALE: return "STALE";
        case NodeMode::QUARANTINED: return "QUARANTINED";
        default: return "UNKNOWN";
    }
}

// Authority Replica State
State gState{10, 0, 0, 0, false};
EvidenceLedger gLedger;
LocalClock gClock{2000, 1, false};
NodeMode gMode = NodeMode::ACTIVE;
Program gProgram = Program::transfer_r0_to_r1();
std::map<std::string, std::string> gVoteLocks; // pre_state_hash -> proposal_hash
std::set<std::string> gAppliedQCs;

struct EvaluatedProposal {
    Proposal p{};
    Certificate cert{};
    std::string prop_digest{};
    std::string cert_hash{};
    std::string pre_st_hash{};
    std::string prop_st_hash{};
    std::string pre_ev_root{};
    uint64_t ev_step{0};
    bool active{false};
} gLastEvaluated;

struct PendingQC {
    std::string uow_id{};
    uint64_t threshold{0};
    std::string expected_ev_root{};
    std::string claimed_qc_hash{};
    std::vector<std::string> voters{};
    std::vector<std::string> vote_hashes{};
    bool active{false};
} gPendingQC;

// Helper: parse uint64_t
bool parse_u64(const std::string& s, uint64_t& out) {
    if (s.empty()) return false;
    uint64_t v = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        v = v * 10 + (c - '0');
    }
    out = v;
    return true;
}

// Helper: split string by delimiter without sstream
std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> elems;
    size_t start = 0;
    while (start < s.size()) {
        size_t pos = s.find(delim, start);
        if (pos == std::string::npos) pos = s.size();
        if (pos > start) {
            elems.push_back(s.substr(start, pos - start));
        }
        start = pos + 1;
    }
    return elems;
}

// Tokenize space-separated command line without sstream
std::vector<std::string> tokenize_line(const std::string& line) {
    std::vector<std::string> parts;
    size_t start = 0;
    while (start < line.size()) {
        while (start < line.size() && (line[start] == ' ' || line[start] == '\t' || line[start] == '\r' || line[start] == '\n')) {
            ++start;
        }
        if (start >= line.size()) break;
        size_t pos = line.find_first_of(" \t\r\n", start);
        if (pos == std::string::npos) pos = line.size();
        parts.push_back(line.substr(start, pos - start));
        start = pos;
    }
    return parts;
}

// Compute canonical AuthorityVote hash
std::string compute_vote_hash(
    bool accepted,
    const std::string& cert_hash,
    uint64_t evidence_step,
    const std::string& node_id,
    const std::string& pre_evidence_root,
    const std::string& pre_state_hash,
    const std::string& proposal_hash,
    const std::string& proposed_state_hash,
    const std::string& rejection_reason,
    const std::string& ruleset_version
) {
    // Canonical key order:
    // accepted, certificate_hash, evidence_step, node_id, pre_evidence_root,
    // pre_state_hash, proposal_hash, proposed_state_hash, rejection_reason, ruleset_version
    std::string s = "{\"accepted\":" + std::string(accepted ? "true" : "false") +
                    ",\"certificate_hash\":\"" + cert_hash + "\"" +
                    ",\"evidence_step\":" + std::to_string(evidence_step) +
                    ",\"node_id\":\"" + node_id + "\"" +
                    ",\"pre_evidence_root\":\"" + pre_evidence_root + "\"" +
                    ",\"pre_state_hash\":\"" + pre_state_hash + "\"" +
                    ",\"proposal_hash\":\"" + proposal_hash + "\"" +
                    ",\"proposed_state_hash\":\"" + proposed_state_hash + "\"";
    if (rejection_reason.empty()) {
        s += ",\"rejection_reason\":null";
    } else {
        s += ",\"rejection_reason\":\"" + rejection_reason + "\"";
    }
    s += ",\"ruleset_version\":\"" + ruleset_version + "\"}";
    return hex_digest(sha256(s));
}

// Compute canonical QuorumCertificate hash
std::string compute_qc_hash(
    const std::string& cert_hash,
    const std::string& committed_state_hash,
    uint64_t evidence_step,
    const std::string& expected_evidence_root,
    const std::string& pre_evidence_root,
    const std::string& pre_state_hash,
    const std::string& proposal_hash,
    const std::string& proposed_state_hash,
    const std::string& ruleset_version,
    uint64_t threshold,
    const std::string& uow_id,
    const std::vector<std::string>& vote_hashes,
    const std::vector<std::string>& voters
) {
    // Canonical key order:
    // certificate_hash, committed_state_hash, evidence_step, expected_evidence_root,
    // pre_evidence_root, pre_state_hash, proposal_hash, proposed_state_hash,
    // ruleset_version, threshold, uow_id, vote_hashes, voters
    std::string s = "{\"certificate_hash\":\"" + cert_hash + "\"" +
                    ",\"committed_state_hash\":\"" + committed_state_hash + "\"" +
                    ",\"evidence_step\":" + std::to_string(evidence_step) +
                    ",\"expected_evidence_root\":\"" + expected_evidence_root + "\"" +
                    ",\"pre_evidence_root\":\"" + pre_evidence_root + "\"" +
                    ",\"pre_state_hash\":\"" + pre_state_hash + "\"" +
                    ",\"proposal_hash\":\"" + proposal_hash + "\"" +
                    ",\"proposed_state_hash\":\"" + proposed_state_hash + "\"" +
                    ",\"ruleset_version\":\"" + ruleset_version + "\"" +
                    ",\"threshold\":" + std::to_string(threshold) +
                    ",\"uow_id\":\"" + uow_id + "\"" +
                    ",\"vote_hashes\":[";
    for (size_t i = 0; i < vote_hashes.size(); ++i) {
        if (i > 0) s += ",";
        s += "\"" + vote_hashes[i] + "\"";
    }
    s += "],\"voters\":[";
    for (size_t i = 0; i < voters.size(); ++i) {
        if (i > 0) s += ",";
        s += "\"" + voters[i] + "\"";
    }
    s += "]}";
    return hex_digest(sha256(s));
}

void emit_line(const std::string& s) {
    Monitor.println(s.c_str());
}

void emit_snapshot(const std::string& event = "auth_snapshot") {
    std::string s = "{\"event\":\"" + event + "\"" +
                    ",\"node_id\":\"" + NODE_ID + "\"" +
                    ",\"mode\":\"" + std::string(mode_string(gMode)) + "\"" +
                    ",\"r0\":" + std::to_string(gState.r0) +
                    ",\"r1\":" + std::to_string(gState.r1) +
                    ",\"pc\":" + std::to_string(gState.pc) +
                    ",\"sequence\":" + std::to_string(gState.sequence) +
                    ",\"halted\":" + (gState.halted ? "true" : "false") +
                    ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                    ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"" +
                    ",\"evidence_steps\":" + std::to_string(gLedger.size()) +
                    ",\"ruleset_version\":\"" + RULESET_VERSION + "\"" +
                    ",\"local_clock\":" + std::to_string(gClock.read()) + "}";
    emit_line(s);
}

} // namespace

void handle_cmd(const std::string& raw) {
    std::vector<std::string> parts = tokenize_line(raw);
    if (parts.empty()) return;

    std::string cmd = parts[0];
    std::transform(cmd.begin(), cmd.end(), cmd.begin(), ::toupper);

    if (cmd == "AUTH_RESET" || cmd == "RESET") {
        uint64_t r0 = 10, r1 = 0;
        if (parts.size() >= 3) {
            parse_u64(parts[1], r0);
            parse_u64(parts[2], r1);
        }
        gState = State{r0, r1, 0, 0, false};
        gLedger = EvidenceLedger();
        gVoteLocks.clear();
        gAppliedQCs.clear();
        gMode = NodeMode::ACTIVE;
        emit_snapshot("auth_reset");
        return;
    }

    if (cmd == "AUTH_SNAPSHOT" || cmd == "SNAPSHOT" || cmd == "STATUS") {
        emit_snapshot("auth_snapshot");
        return;
    }

    if (cmd == "AUTH_CLOCK" || cmd == "CLOCKS") {
        uint64_t stride = 1;
        uint64_t frozen = 0;
        if (parts.size() >= 2) parse_u64(parts[1], stride);
        if (parts.size() >= 3) parse_u64(parts[2], frozen);
        gClock.stride = stride;
        gClock.frozen = (frozen != 0);
        std::string s = "{\"event\":\"auth_clock\",\"node_id\":\"" + NODE_ID + "\"" +
                        ",\"stride\":" + std::to_string(gClock.stride) +
                        ",\"frozen\":" + (gClock.frozen ? "true" : "false") +
                        ",\"local_clock\":" + std::to_string(gClock.read()) + "}";
        emit_line(s);
        return;
    }

    if (cmd == "AUTH_QUARANTINE") {
        gMode = NodeMode::QUARANTINED;
        std::string s = "{\"event\":\"auth_quarantine\",\"node_id\":\"" + NODE_ID + "\",\"mode\":\"QUARANTINED\"}";
        emit_line(s);
        return;
    }

    if (cmd == "AUTH_REBUILD" && parts.size() >= 6) {
        uint64_t r0 = 0, r1 = 0, pc = 0, seq = 0, steps = 0;
        std::string root_hex;
        if (parts.size() >= 7) {
            parse_u64(parts[1], r0);
            parse_u64(parts[2], r1);
            parse_u64(parts[3], pc);
            parse_u64(parts[4], seq);
            root_hex = parts[5];
            parse_u64(parts[6], steps);
        } else {
            parse_u64(parts[1], r0);
            parse_u64(parts[2], r1);
            parse_u64(parts[3], seq);
            root_hex = parts[4];
            parse_u64(parts[5], steps);
        }
        std::array<uint8_t, 32> root_bytes{};
        parse_hex_digest(root_hex, root_bytes);
        gState = State{r0, r1, static_cast<uint32_t>(pc), seq, false};
        gLedger = EvidenceLedger();
        gLedger.restore_checkpoint(root_bytes, static_cast<size_t>(steps));
        gVoteLocks.clear();
        gMode = NodeMode::ACTIVE;
        emit_snapshot("auth_rebuild");
        return;
    }

    if (cmd == "AUTH_EVALUATE" && parts.size() >= 9) {
        // AUTH_EVALUATE <prehash> <r0> <r1> <pc> <sequence> <halted> <selected_pc> <proposal_hash>
        Proposal p{};
        uint64_t r0 = 0, r1 = 0, pc = 0, seq = 0, halted = 0, selected_pc = 0;
        if (!parse_hex_digest(parts[1], p.pre_state_hash)
            || !parse_u64(parts[2], r0)
            || !parse_u64(parts[3], r1)
            || !parse_u64(parts[4], pc)
            || !parse_u64(parts[5], seq)
            || !parse_u64(parts[6], halted)
            || !parse_u64(parts[7], selected_pc)
            || !parse_hex_digest(parts[8], p.proposal_hash)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad AUTH_EVALUATE envelope\"}");
            return;
        }
        p.proposed = State{r0, r1, static_cast<uint32_t>(pc), seq, halted != 0};
        p.selected_pc = static_cast<uint32_t>(selected_pc);
        p.halted = (halted != 0);

        const std::string cur_state_hash = hex_digest(hash_state(gState));
        const std::string prop_digest = parts[8];
        const std::string pre_ev_root = hex_digest(gLedger.root());
        const uint64_t ev_step = gLedger.size();

        bool accepted = false;
        std::string reason = "";
        std::string cert_hash = "";

        if (gMode == NodeMode::QUARANTINED) {
            reason = "NODE_QUARANTINED";
        } else if (parts[1] != cur_state_hash) {
            reason = "PRE_STATE_MISMATCH";
        } else {
            auto it = gVoteLocks.find(cur_state_hash);
            if (it != gVoteLocks.end() && it->second != prop_digest) {
                reason = "CONFLICTING_VOTE_LOCK";
            } else {
                Certificate cert = certify(gProgram, gState, p);
                if (!cert.valid) {
                    reason = reject_reason_string(cert.reason);
                } else {
                    accepted = true;
                    cert_hash = hex_digest(cert.certificate_hash);
                    gVoteLocks[cur_state_hash] = prop_digest;
                    gLastEvaluated.p = p;
                    gLastEvaluated.cert = cert;
                    gLastEvaluated.prop_digest = prop_digest;
                    gLastEvaluated.cert_hash = cert_hash;
                    gLastEvaluated.pre_st_hash = cur_state_hash;
                    gLastEvaluated.prop_st_hash = hex_digest(hash_state(p.proposed));
                    gLastEvaluated.pre_ev_root = pre_ev_root;
                    gLastEvaluated.ev_step = ev_step;
                    gLastEvaluated.active = true;
                }
            }
        }

        gClock.advance();
        const std::string vote_hash = compute_vote_hash(
            accepted, cert_hash, ev_step, NODE_ID, pre_ev_root,
            cur_state_hash, prop_digest, hex_digest(hash_state(p.proposed)),
            reason, RULESET_VERSION
        );

        std::string s = "{\"event\":\"auth_vote\""
                        ",\"node_id\":\"" + NODE_ID + "\"" +
                        ",\"accepted\":" + (accepted ? "true" : "false");
        if (reason.empty()) s += ",\"reason\":null";
        else s += ",\"reason\":\"" + reason + "\"";
        s += ",\"proposal_hash\":\"" + prop_digest + "\"" +
             ",\"pre_state_hash\":\"" + cur_state_hash + "\"" +
             ",\"proposed_state_hash\":\"" + hex_digest(hash_state(p.proposed)) + "\"" +
             ",\"certificate_hash\":\"" + cert_hash + "\"" +
             ",\"pre_evidence_root\":\"" + pre_ev_root + "\"" +
             ",\"evidence_step\":" + std::to_string(ev_step) +
             ",\"ruleset_version\":\"" + RULESET_VERSION + "\"" +
             ",\"vote_hash\":\"" + vote_hash + "\"" +
             ",\"local_clock\":" + std::to_string(gClock.read()) + "}";
        emit_line(s);
        return;
    }

    if (cmd == "AUTH_QC_BEGIN" && parts.size() >= 5) {
        gPendingQC.uow_id = parts[1];
        parse_u64(parts[2], gPendingQC.threshold);
        gPendingQC.expected_ev_root = parts[3];
        gPendingQC.claimed_qc_hash = parts[4];
        gPendingQC.voters.clear();
        gPendingQC.vote_hashes.clear();
        gPendingQC.active = true;
        emit_line("{\"event\":\"auth_qc_begin\",\"status\":\"ok\"}");
        return;
    }

    if (cmd == "AUTH_QC_VOTE" && parts.size() >= 3) {
        if (gPendingQC.active) {
            gPendingQC.voters.push_back(parts[1]);
            gPendingQC.vote_hashes.push_back(parts[2]);
            emit_line("{\"event\":\"auth_qc_vote\",\"status\":\"ok\",\"count\":" + std::to_string(gPendingQC.voters.size()) + "}");
        } else {
            emit_line("{\"event\":\"error\",\"reason\":\"no active pending QC\"}");
        }
        return;
    }

    if (cmd == "AUTH_QC_APPLY" && parts.size() >= 2) {
        if (gMode == NodeMode::QUARANTINED) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"NODE_QUARANTINED\",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}");
            return;
        }
        if (!gPendingQC.active || !gLastEvaluated.active || gLastEvaluated.prop_digest != parts[1]) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"NO_MATCHING_EVALUATED_PROPOSAL\"}");
            return;
        }
        if (gAppliedQCs.count(gPendingQC.claimed_qc_hash) > 0) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":true,\"reason\":\"ALREADY_APPLIED\",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}");
            return;
        }
        if (gPendingQC.voters.size() < gPendingQC.threshold) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"INSUFFICIENT_QUORUM\"}");
            return;
        }
        std::set<std::string> unique_voters(gPendingQC.voters.begin(), gPendingQC.voters.end());
        if (unique_voters.size() != gPendingQC.voters.size()) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"DUPLICATE_VOTER\"}");
            return;
        }
        std::string expected_hash = compute_qc_hash(
            gLastEvaluated.cert_hash, gLastEvaluated.prop_st_hash, gLastEvaluated.ev_step,
            gPendingQC.expected_ev_root, gLastEvaluated.pre_ev_root, gLastEvaluated.pre_st_hash,
            gLastEvaluated.prop_digest, gLastEvaluated.prop_st_hash, RULESET_VERSION,
            gPendingQC.threshold, gPendingQC.uow_id, gPendingQC.vote_hashes, gPendingQC.voters
        );
        if (expected_hash != gPendingQC.claimed_qc_hash) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"QC_HASH_MISMATCH\"}");
            return;
        }
        StepResult res = commit(gProgram, gState, gLastEvaluated.p, gLedger);
        if (!res.committed) {
            emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":false,\"idempotent\":false,\"reason\":\"COMMIT_REJECTED\"}");
            return;
        }
        gState = res.state;
        gAppliedQCs.insert(gPendingQC.claimed_qc_hash);
        gMode = NodeMode::ACTIVE;
        gPendingQC.active = false;
        gLastEvaluated.active = false;
        emit_line("{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\",\"applied\":true,\"idempotent\":false,\"reason\":\"APPLIED\",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\",\"sequence\":" + std::to_string(gState.sequence) + "}");
        return;
    }

    if (cmd == "AUTH_APPLY_QC" && parts.size() >= 14) {
        std::string uow_id = parts[1];
        std::string prop_hash = parts[2];
        std::string pre_st_hash = parts[3];
        std::string prop_st_hash = parts[4];
        std::string comm_st_hash = parts[5];
        std::string cert_hash = parts[6];
        std::string pre_ev_root = parts[7];
        uint64_t ev_step = 0; parse_u64(parts[8], ev_step);
        std::string exp_ev_root = parts[9];
        uint64_t threshold = 0; parse_u64(parts[10], threshold);
        std::vector<std::string> voters = split(parts[11], ',');
        std::vector<std::string> vote_hashes = split(parts[12], ',');
        std::string claimed_qc_hash = parts[13];

        if (gMode == NodeMode::QUARANTINED) {
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":false,\"reason\":\"NODE_QUARANTINED\"" +
                            ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                            ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}";
            emit_line(s);
            return;
        }

        if (gAppliedQCs.count(claimed_qc_hash) > 0) {
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":true,\"reason\":\"ALREADY_APPLIED\"" +
                            ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                            ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}";
            emit_line(s);
            return;
        }

        std::string expected_hash = compute_qc_hash(
            cert_hash, comm_st_hash, ev_step, exp_ev_root, pre_ev_root,
            pre_st_hash, prop_hash, prop_st_hash, RULESET_VERSION,
            threshold, uow_id, vote_hashes, voters
        );
        if (expected_hash != claimed_qc_hash) {
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":false,\"reason\":\"QC_HASH_MISMATCH\"" +
                            ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                            ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"}";
            emit_line(s);
            return;
        }

        std::string cur_st_hash = hex_digest(hash_state(gState));
        std::string cur_ev_root = hex_digest(gLedger.root());
        if (cur_st_hash == comm_st_hash && cur_ev_root == exp_ev_root) {
            gAppliedQCs.insert(claimed_qc_hash);
            gMode = NodeMode::ACTIVE;
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":true,\"reason\":\"STATE_ALREADY_AT_QUORUM_TIP\"" +
                            ",\"state_hash\":\"" + cur_st_hash + "\"" +
                            ",\"evidence_root\":\"" + cur_ev_root + "\"}";
            emit_line(s);
            return;
        }

        if (cur_st_hash != pre_st_hash) {
            gMode = NodeMode::STALE;
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":false,\"reason\":\"PRE_STATE_MISMATCH\"" +
                            ",\"state_hash\":\"" + cur_st_hash + "\"" +
                            ",\"evidence_root\":\"" + cur_ev_root + "\"}";
            emit_line(s);
            return;
        }

        if (cur_ev_root != pre_ev_root || gLedger.size() != ev_step) {
            gMode = NodeMode::QUARANTINED;
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":false,\"reason\":\"PRE_EVIDENCE_ROOT_MISMATCH\"" +
                            ",\"state_hash\":\"" + cur_st_hash + "\"" +
                            ",\"evidence_root\":\"" + cur_ev_root + "\"}";
            emit_line(s);
            return;
        }

        Proposal p{};
        parse_hex_digest(pre_st_hash, p.pre_state_hash);
        parse_hex_digest(prop_hash, p.proposal_hash);
        StepResult res = commit(gProgram, gState, p, gLedger);
        if (!res.committed) {
            std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                            ",\"applied\":false,\"idempotent\":false,\"reason\":\"COMMIT_REJECTED\"" +
                            ",\"state_hash\":\"" + cur_st_hash + "\"" +
                            ",\"evidence_root\":\"" + cur_ev_root + "\"}";
            emit_line(s);
            return;
        }

        gState = res.state;
        gAppliedQCs.insert(claimed_qc_hash);
        gMode = NodeMode::ACTIVE;

        std::string s = "{\"event\":\"auth_apply\",\"node_id\":\"" + NODE_ID + "\"" +
                        ",\"applied\":true,\"idempotent\":false,\"reason\":\"APPLIED\"" +
                        ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                        ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"" +
                        ",\"sequence\":" + std::to_string(gState.sequence) + "}";
        emit_line(s);
        return;
    }

    if (cmd == "EXT_PROPOSE" && parts.size() >= 9) {
        Proposal p{};
        uint64_t r0 = 0, r1 = 0, pc = 0, seq = 0, halted = 0, selected_pc = 0;
        if (!parse_hex_digest(parts[1], p.pre_state_hash)
            || !parse_u64(parts[2], r0)
            || !parse_u64(parts[3], r1)
            || !parse_u64(parts[4], pc)
            || !parse_u64(parts[5], seq)
            || !parse_u64(parts[6], halted)
            || !parse_u64(parts[7], selected_pc)
            || !parse_hex_digest(parts[8], p.proposal_hash)) {
            emit_line("{\"event\":\"error\",\"reason\":\"bad EXT_PROPOSE envelope\"}");
            return;
        }
        p.proposed = State{r0, r1, static_cast<uint32_t>(pc), seq, halted != 0};
        p.selected_pc = static_cast<uint32_t>(selected_pc);
        p.halted = (halted != 0);

        StepResult res = commit(gProgram, gState, p, gLedger);
        if (res.committed) {
            gState = res.state;
        }
        std::string s = "{\"event\":\"decision\""
                        ",\"node_id\":\"" + NODE_ID + "\"" +
                        ",\"committed\":" + (res.committed ? "true" : "false") +
                        ",\"reason\":\"" + std::string(reject_reason_string(res.certificate.reason)) + "\"" +
                        ",\"r0\":" + std::to_string(gState.r0) +
                        ",\"r1\":" + std::to_string(gState.r1) +
                        ",\"pc\":" + std::to_string(gState.pc) +
                        ",\"sequence\":" + std::to_string(gState.sequence) +
                        ",\"halted\":" + (gState.halted ? "true" : "false") +
                        ",\"state_hash\":\"" + hex_digest(hash_state(gState)) + "\"" +
                        ",\"evidence_root\":\"" + hex_digest(gLedger.root()) + "\"" +
                        ",\"proposal_hash\":\"" + parts[8] + "\"" +
                        ",\"certificate_hash\":\"" + hex_digest(res.certificate.certificate_hash) + "\"}";
        emit_line(s);
        return;
    }

    emit_line("{\"event\":\"error\",\"reason\":\"unknown command\"}");
}

void setup() {
    Bridge.begin();
    Monitor.begin(115200);
}

void loop() {
    if (Monitor.available() > 0) {
        String s = Monitor.readStringUntil('\n');
        s.trim();
        if (s.length() > 0) {
            handle_cmd(s.c_str());
        }
    }
    delay(5);
}
