#pragma once

#include "uow_native_types.hpp"
#include <vector>
#include <string>

namespace uow_native {

struct NativeEvidenceRecord {
    int64_t step_number{0};
    std::string uow_id{};
    std::string source_category{"Processes"};
    std::string target_category{"Data"};
    std::string pre_state_hash{};
    int64_t selected_route_index{0};
    std::string proposed_state_hash{};
    std::string certificate_hash{};
    std::string post_state_hash{};
    TypedValue next_uow_pointer{nullptr};
    std::string prev_evidence_hash{};
    std::string record_hash{};

    std::string calculate_hash() const;
};

class NativeEvidenceLedger {
public:
    NativeEvidenceLedger() = default;

    std::string root_hash() const;
    void append(const NativeEvidenceRecord& record);
    bool verify_integrity() const;

    const std::vector<NativeEvidenceRecord>& records() const { return records_; }
    size_t size() const { return records_.size(); }

private:
    std::vector<NativeEvidenceRecord> records_{};
};

} // namespace uow_native
