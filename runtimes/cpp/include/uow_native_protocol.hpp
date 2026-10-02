#pragma once

#include "uow_native_types.hpp"
#include "uow_native_state.hpp"
#include "uow_native_evidence.hpp"
#include "uow_native_idempotency.hpp"

namespace uow_native {

class NativeProtocolExecutor {
public:
    NativeProtocolExecutor();

    TypedValue execute_envelope(const TypedValue& envelope);
    TypedValue execute_chain(const TypedValue& initial_state_val, const TypedValue& steps_val);
    TypedValue dispatch_vector(const TypedValue& vector_json);

private:
    NativeIdempotencyStore idempotency_store_{};

    TypedValue make_error_envelope(
        const std::string& req_id,
        const std::string& op,
        const std::string& err_code,
        const std::string& err_msg,
        const TypedValue& result_extra = TypedValue(std::map<std::string, TypedValue>{})
    );
};

} // namespace uow_native
