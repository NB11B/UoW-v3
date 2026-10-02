#pragma once

#include "uow_native_types.hpp"
#include <map>
#include <string>

namespace uow_native {

struct CachedResponse {
    std::string request_id{};
    std::string operation{};
    std::string status{};
    TypedValue result{};
    TypedValue evidence{};
    TypedValue execution_metadata{};
    TypedValue errors{std::vector<TypedValue>{}};
    std::string payload_fingerprint{};
};

class NativeIdempotencyStore {
public:
    NativeIdempotencyStore();

    bool has(const std::string& key) const;
    const CachedResponse* get(const std::string& key) const;
    void put(const std::string& key, const CachedResponse& resp);
    bool is_conflicting_payload(const std::string& key, const TypedValue& payload) const;

private:
    std::map<std::string, CachedResponse> store_{};
};

} // namespace uow_native
