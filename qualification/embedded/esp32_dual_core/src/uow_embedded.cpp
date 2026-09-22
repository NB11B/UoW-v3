#include "uow_embedded.hpp"

#include <algorithm>
#include <cstring>
#include <sstream>
#include <stdexcept>

namespace uow_embedded {
namespace {

inline uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}

constexpr uint32_t K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

std::string state_canonical(const State& s) {
    std::ostringstream o;
    o << "r0=" << s.r0
      << ";r1=" << s.r1
      << ";pc=" << s.pc
      << ";sequence=" << s.sequence
      << ";halted=" << (s.halted ? 1 : 0);
    return o.str();
}

bool state_equal(const State& a, const State& b) {
    return a.r0 == b.r0 && a.r1 == b.r1 && a.pc == b.pc &&
           a.sequence == b.sequence && a.halted == b.halted;
}

State expected_successor(const Program& program, const State& s) {
    if (s.halted) return s;
    const auto& ins = program.at(s.pc);
    State out = s;
    out.sequence += 1;

    switch (ins.op) {
        case Op::INC: {
            uint64_t& reg = (ins.reg == 0) ? out.r0 : out.r1;
            reg += 1;
            out.pc = ins.a;
            break;
        }
        case Op::DECJZ: {
            uint64_t& reg = (ins.reg == 0) ? out.r0 : out.r1;
            if (reg == 0) {
                out.pc = ins.a;
            } else {
                reg -= 1;
                out.pc = ins.b;
            }
            break;
        }
        case Op::HALT:
            out.halted = true;
            break;
    }
    return out;
}

} // namespace

void LocalClock::advance() {
    if (!frozen) ticks += stride;
}

const Instruction& Program::at(uint32_t pc) const {
    if (pc >= code_.size()) throw std::out_of_range("program counter out of range");
    return code_[pc];
}

Program Program::transfer_r0_to_r1() {
    return Program({
        {Op::DECJZ, 0, 2, 1},
        {Op::INC,   1, 0, 0},
        {Op::HALT,  0, 0, 0},
    });
}

std::array<uint8_t, 32> sha256(const uint8_t* data, size_t len) {
    std::array<uint32_t, 8> h = {
        0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
    };

    const uint64_t bit_len = static_cast<uint64_t>(len) * 8ULL;
    size_t total = len + 1 + 8;
    size_t padded = ((total + 63) / 64) * 64;
    std::vector<uint8_t> msg(padded, 0);
    if (len) std::memcpy(msg.data(), data, len);
    msg[len] = 0x80;
    for (int i = 0; i < 8; ++i) {
        msg[padded - 1 - i] = static_cast<uint8_t>(bit_len >> (8 * i));
    }

    for (size_t off = 0; off < padded; off += 64) {
        uint32_t w[64]{};
        for (int i = 0; i < 16; ++i) {
            const size_t j = off + i * 4;
            w[i] = (static_cast<uint32_t>(msg[j]) << 24) |
                   (static_cast<uint32_t>(msg[j+1]) << 16) |
                   (static_cast<uint32_t>(msg[j+2]) << 8) |
                   static_cast<uint32_t>(msg[j+3]);
        }
        for (int i = 16; i < 64; ++i) {
            const uint32_t s0 = rotr(w[i-15], 7) ^ rotr(w[i-15], 18) ^ (w[i-15] >> 3);
            const uint32_t s1 = rotr(w[i-2], 17) ^ rotr(w[i-2], 19) ^ (w[i-2] >> 10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }

        uint32_t a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], hh=h[7];
        for (int i = 0; i < 64; ++i) {
            const uint32_t S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
            const uint32_t ch = (e & f) ^ ((~e) & g);
            const uint32_t temp1 = hh + S1 + ch + K[i] + w[i];
            const uint32_t S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
            const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const uint32_t temp2 = S0 + maj;
            hh=g; g=f; f=e; e=d+temp1; d=c; c=b; b=a; a=temp1+temp2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d;
        h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
    }

    std::array<uint8_t, 32> out{};
    for (size_t i = 0; i < 8; ++i) {
        out[i*4+0] = static_cast<uint8_t>(h[i] >> 24);
        out[i*4+1] = static_cast<uint8_t>(h[i] >> 16);
        out[i*4+2] = static_cast<uint8_t>(h[i] >> 8);
        out[i*4+3] = static_cast<uint8_t>(h[i]);
    }
    return out;
}

std::array<uint8_t, 32> sha256(const std::string& text) {
    return sha256(reinterpret_cast<const uint8_t*>(text.data()), text.size());
}

std::string hex_digest(const std::array<uint8_t, 32>& d) {
    static constexpr char H[] = "0123456789abcdef";
    std::string out;
    out.resize(64);
    for (size_t i = 0; i < 32; ++i) {
        out[i*2] = H[d[i] >> 4];
        out[i*2+1] = H[d[i] & 0x0f];
    }
    return out;
}

std::array<uint8_t, 32> hash_state(const State& s) {
    return sha256(state_canonical(s));
}

std::array<uint8_t, 32> hash_proposal_body(const Proposal& p) {
    std::ostringstream o;
    o << "pre=" << hex_digest(p.pre_state_hash)
      << ";post=" << hex_digest(hash_state(p.proposed))
      << ";pc=" << p.selected_pc
      << ";halted=" << (p.halted ? 1 : 0);
    return sha256(o.str());
}

std::array<uint8_t, 32> hash_certificate_body(
    const Proposal& p, bool valid, RejectReason reason) {
    std::ostringstream o;
    o << "proposal=" << hex_digest(p.proposal_hash)
      << ";valid=" << (valid ? 1 : 0)
      << ";reason=" << static_cast<unsigned>(reason);
    return sha256(o.str());
}

std::array<uint8_t, 32> hash_evidence_body(const EvidenceRecord& r) {
    std::ostringstream o;
    o << "step=" << r.step
      << ";pre=" << hex_digest(r.pre_state_hash)
      << ";post=" << hex_digest(r.post_state_hash)
      << ";proposal=" << hex_digest(r.proposal_hash)
      << ";certificate=" << hex_digest(r.certificate_hash)
      << ";prev=" << hex_digest(r.prev_record_hash);
    return sha256(o.str());
}

Proposal propose(
    const Program& program,
    const State& authoritative_snapshot,
    const LocalClock& proposer_clock,
    FaultMode fault) {
    Proposal p{};
    p.pre_state_hash = hash_state(authoritative_snapshot);
    p.proposed = expected_successor(program, authoritative_snapshot);
    p.selected_pc = p.proposed.pc;
    p.halted = p.proposed.halted;
    p.proposer_clock = proposer_clock.read();

    if (fault == FaultMode::TAMPER_STATE) {
        p.proposed.r1 += 1;
    } else if (fault == FaultMode::TAMPER_PREHASH) {
        p.pre_state_hash[0] ^= 0xff;
    } else if (fault == FaultMode::TAMPER_ROUTE) {
        p.selected_pc += 1;
    }

    p.proposal_hash = hash_proposal_body(p);
    return p;
}

Certificate certify(
    const Program& program,
    const State& authoritative_state,
    const Proposal& proposal) {
    Certificate c{};
    const auto current_hash = hash_state(authoritative_state);
    const auto expected = propose(program, authoritative_state, LocalClock{}, FaultMode::NONE);

    if (proposal.pre_state_hash != current_hash) {
        c.reason = RejectReason::STALE_PRE_STATE;
    } else if (!state_equal(proposal.proposed, expected.proposed)) {
        c.reason = RejectReason::STATE_DIVERGENCE;
    } else if (proposal.selected_pc != expected.selected_pc) {
        c.reason = RejectReason::ROUTE_DIVERGENCE;
    } else if (proposal.halted != expected.halted) {
        c.reason = RejectReason::HALT_DIVERGENCE;
    } else if (proposal.proposal_hash != hash_proposal_body(proposal)) {
        c.reason = RejectReason::PROPOSAL_HASH_DIVERGENCE;
    } else {
        c.valid = true;
        c.reason = RejectReason::NONE;
    }

    c.certificate_hash = hash_certificate_body(proposal, c.valid, c.reason);
    return c;
}

bool EvidenceLedger::append(const EvidenceRecord& record) {
    if (record.step != size_ + 1) { valid_ = false; return false; }
    if (record.prev_record_hash != root_) { valid_ = false; return false; }
    if (record.record_hash != hash_evidence_body(record)) { valid_ = false; return false; }
    root_ = record.record_hash;
    ++size_;
    if (retain_records_) records_.push_back(record);
    return true;
}

bool EvidenceLedger::verify() const {
    if (!valid_) return false;
    if (!retain_records_) return true;
    std::array<uint8_t, 32> prev{};
    uint64_t step = 1;
    for (const auto& r : records_) {
        if (r.step != step++) return false;
        if (r.prev_record_hash != prev) return false;
        if (r.record_hash != hash_evidence_body(r)) return false;
        prev = r.record_hash;
    }
    return records_.size() == size_ && prev == root_;
}

const std::array<uint8_t, 32>& EvidenceLedger::root() const {
    return root_;
}

StepResult commit(
    const Program& program,
    const State& authoritative_state,
    const Proposal& proposal,
    EvidenceLedger& ledger) {
    StepResult out{};
    out.state = authoritative_state;
    out.certificate = certify(program, authoritative_state, proposal);
    if (!out.certificate.valid) return out;

    EvidenceRecord r{};
    r.step = ledger.size() + 1;
    r.pre_state_hash = hash_state(authoritative_state);
    r.post_state_hash = hash_state(proposal.proposed);
    r.proposal_hash = proposal.proposal_hash;
    r.certificate_hash = out.certificate.certificate_hash;
    r.prev_record_hash = ledger.root();
    r.record_hash = hash_evidence_body(r);

    if (!ledger.append(r)) {
        out.certificate.valid = false;
        out.certificate.reason = RejectReason::PROPOSAL_HASH_DIVERGENCE;
        return out;
    }

    out.committed = true;
    out.evidence = r;
    out.state = proposal.proposed;
    return out;
}

StepResult execute_one(
    const Program& program,
    const State& authoritative_state,
    LocalClock& proposer_clock,
    LocalClock& authority_clock,
    EvidenceLedger& ledger,
    FaultMode fault) {
    proposer_clock.advance();
    const auto p = propose(program, authoritative_state, proposer_clock, fault);
    authority_clock.advance();
    return commit(program, authoritative_state, p, ledger);
}

const char* reject_reason_string(RejectReason reason) {
    switch (reason) {
        case RejectReason::NONE: return "NONE";
        case RejectReason::STALE_PRE_STATE: return "STALE_PRE_STATE";
        case RejectReason::STATE_DIVERGENCE: return "STATE_DIVERGENCE";
        case RejectReason::ROUTE_DIVERGENCE: return "ROUTE_DIVERGENCE";
        case RejectReason::HALT_DIVERGENCE: return "HALT_DIVERGENCE";
        case RejectReason::PROPOSAL_HASH_DIVERGENCE: return "PROPOSAL_HASH_DIVERGENCE";
    }
    return "UNKNOWN";
}

const char* fault_mode_string(FaultMode mode) {
    switch (mode) {
        case FaultMode::NONE: return "NONE";
        case FaultMode::TAMPER_STATE: return "TAMPER_STATE";
        case FaultMode::TAMPER_PREHASH: return "TAMPER_PREHASH";
        case FaultMode::TAMPER_ROUTE: return "TAMPER_ROUTE";
    }
    return "NONE";
}

FaultMode parse_fault_mode(const std::string& text) {
    if (text == "TAMPER_STATE") return FaultMode::TAMPER_STATE;
    if (text == "TAMPER_PREHASH") return FaultMode::TAMPER_PREHASH;
    if (text == "TAMPER_ROUTE") return FaultMode::TAMPER_ROUTE;
    return FaultMode::NONE;
}

} // namespace uow_embedded
