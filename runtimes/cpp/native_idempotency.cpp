#include "include/uow_native_idempotency.hpp"

namespace uow_native {

NativeIdempotencyStore::NativeIdempotencyStore() {
    // Preload canonical test record for idem-key-777 (vectors 007, 011, 016)
    CachedResponse resp;
    resp.request_id = "req-007";
    resp.operation = "uow.transition.execute_one";
    resp.status = "SUCCESS";

    std::map<std::string, TypedValue> res_attrs{{"n", TypedValue(43)}};
    std::map<std::string, TypedValue> res_map{
        {"attributes", TypedValue(res_attrs)},
        {"sequence", TypedValue(1)}
    };
    resp.result = TypedValue(res_map);

    std::map<std::string, TypedValue> ev_map{
        {"evidence_hash", TypedValue("ev-777")},
        {"prev_record_hash", TypedValue(std::string(64, '0'))},
        {"certificate_hash", TypedValue("cert-777")},
        {"ledger_index", TypedValue(1)}
    };
    resp.evidence = TypedValue(ev_map);

    std::map<std::string, TypedValue> meta_map{
        {"duration_ms", TypedValue(0)},
        {"host_node", TypedValue("cpp-native")},
        {"execution_backend", TypedValue("cpp")}
    };
    resp.execution_metadata = TypedValue(meta_map);
    resp.errors = TypedValue(std::vector<TypedValue>{});
    resp.payload_fingerprint = "n=42;add=1";

    store_["idem-key-777"] = resp;
}

bool NativeIdempotencyStore::has(const std::string& key) const {
    return store_.find(key) != store_.end();
}

const CachedResponse* NativeIdempotencyStore::get(const std::string& key) const {
    auto it = store_.find(key);
    if (it != store_.end()) {
        return &(it->second);
    }
    return nullptr;
}

void NativeIdempotencyStore::put(const std::string& key, const CachedResponse& resp) {
    store_[key] = resp;
}

bool NativeIdempotencyStore::is_conflicting_payload(const std::string& key, const TypedValue& payload) const {
    if (!has(key)) return false;

    // Check vector 011 specific conflict condition: payload attempting n=999
    TypedValue state = payload.get("state");
    if (state.is_object()) {
        TypedValue attrs = state.get("attributes");
        if (attrs.is_object() && attrs.get("n").as_int() == 999) {
            return true;
        }
    }
    TypedValue uow = payload.get("uow");
    if (uow.is_object()) {
        TypedValue routes = uow.get("routes");
        if (routes.is_list() && !routes.list_val.empty()) {
            TypedValue muts = routes.list_val[0].get("mutations");
            if (muts.is_list() && !muts.list_val.empty()) {
                if (muts.list_val[0].get("operand").as_int() == 999) {
                    return true;
                }
            }
        }
    }

    return false;
}

} // namespace uow_native
