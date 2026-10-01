/**
 * @file uow.h
 * @brief Canonical C ABI Boundary for Unit-of-Work (UoW) v2.0
 *
 * Provides a portable, foreign-function-interface (FFI) boundary for linking
 * UoW execution into C, C++, Pascal/Delphi, Ada, Fortran, Swift, Go (cgo),
 * C# (.NET P/Invoke), and Java (JNI).
 */

#ifndef UOW_H
#define UOW_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

/**
 * Return status codes for C ABI functions.
 */
typedef enum {
    UOW_STATUS_OK = 0,
    UOW_STATUS_INVALID_ARGUMENT = -1,
    UOW_STATUS_PARSE_ERROR = -2,
    UOW_STATUS_GUARD_UNSATISFIED = -3,
    UOW_STATUS_STALE_PRE_STATE = -4,
    UOW_STATUS_ROUTE_DIVERGENCE = -5,
    UOW_STATUS_AUTHORITY_DENIED = -6,
    UOW_STATUS_INTERNAL_ERROR = -99
} uow_status_t;

/**
 * Frees a heap-allocated string returned by any UoW C ABI function.
 *
 * @param ptr Pointer to string allocated by UoW runtime.
 */
void uow_free_string(char* ptr);

/**
 * Validates whether a JSON string conforms to the canonical UoWEnvelope schema.
 *
 * @param envelope_json Null-terminated UTF-8 JSON string.
 * @return 0 if valid, positive error code if schema invalid, negative if null/malformed.
 */
int uow_validate_envelope(const char* envelope_json);

/**
 * Executes a single-shot Unit-of-Work under the canonical envelope.
 *
 * @param envelope_json Null-terminated UTF-8 JSON string matching UoWEnvelope.
 * @param result_json_out Pointer receiving newly allocated UTF-8 JSON string of UoWResult.
 *                        Caller must release via uow_free_string().
 * @return UOW_STATUS_OK on execution dispatch, or specific failure status code.
 */
uow_status_t uow_execute(const char* envelope_json, char** result_json_out);

/**
 * Verifies whether a given evidence hash chain is unbroken and internally valid.
 *
 * @param evidence_records_json Array of EvidenceRecord objects serialized as JSON.
 * @param is_valid_out Pointer receiving 1 if valid, 0 if corrupted or chain broken.
 * @return UOW_STATUS_OK on evaluation, or negative error code.
 */
uow_status_t uow_verify_evidence(const char* evidence_records_json, int* is_valid_out);

#ifdef __cplusplus
}
#endif

#endif /* UOW_H */
