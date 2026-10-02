#include "include/uow_native_evidence.hpp"
#include <stdexcept>

namespace uow_native {

std::string NativeEvidenceRecord::calculate_hash() const {
    TypedValue payload(std::map<std::string, TypedValue>{
        {"certificate_hash", TypedValue(certificate_hash)},
        {"next_uow_pointer", next_uow_pointer},
        {"post_state_hash", TypedValue(post_state_hash)},
        {"pre_state_hash", TypedValue(pre_state_hash)},
        {"prev_evidence_hash", TypedValue(prev_evidence_hash)},
        {"proposed_state_hash", TypedValue(proposed_state_hash)},
        {"selected_route_index", TypedValue(selected_route_index)},
        {"source_category", TypedValue(source_category)},
        {"step_number", TypedValue(step_number)},
        {"target_category", TypedValue(target_category)},
        {"uow_id", TypedValue(uow_id)}
    });
    std::string canonical = payload.to_canonical_json();
    return sha256_hex(canonical);
}

std::string NativeEvidenceLedger::root_hash() const {
    if (records_.empty()) {
        return std::string(64, '0');
    }
    return records_.back().record_hash;
}

void NativeEvidenceLedger::append(const NativeEvidenceRecord& record) {
    if (record.prev_evidence_hash != root_hash()) {
        throw std::runtime_error("Evidence record does not extend current ledger root");
    }
    if (record.step_number != static_cast<int64_t>(records_.size()) + 1) {
        throw std::runtime_error("Evidence step number is not contiguous");
    }
    NativeEvidenceRecord rec = record;
    if (rec.record_hash.empty()) {
        rec.record_hash = rec.calculate_hash();
    }
    records_.push_back(rec);
}

bool NativeEvidenceLedger::verify_integrity() const {
    std::string prev = std::string(64, '0');
    for (size_t i = 0; i < records_.size(); ++i) {
        const auto& rec = records_[i];
        if (rec.step_number != static_cast<int64_t>(i + 1)) {
            return false;
        }
        if (rec.prev_evidence_hash != prev) {
            return false;
        }
        if (rec.record_hash != rec.calculate_hash()) {
            return false;
        }
        prev = rec.record_hash;
    }
    return true;
}

} // namespace uow_native
