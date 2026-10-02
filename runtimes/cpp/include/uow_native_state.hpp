#pragma once

#include "uow_native_types.hpp"

namespace uow_native {

struct NativeWorldState {
    TypedValue attributes{std::map<std::string, TypedValue>{}};
    TypedValue cursor{nullptr}; // Null or String
    std::string status{"RUNNING"};
    int64_t sequence{0};

    std::string compute_hash() const;
    bool evaluate_guard(const Guard& guard) const;
    void apply_mutation(const Mutation& mutation);

    static NativeWorldState from_typed_value(const TypedValue& val);
    TypedValue to_typed_value() const;
};

} // namespace uow_native
