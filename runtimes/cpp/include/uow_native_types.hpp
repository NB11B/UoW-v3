#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <sstream>
#include <iomanip>
#include <stdexcept>
#include <algorithm>
#include <cstring>
#include <array>

namespace uow_native {

// Forward declarations
struct TypedValue;

enum class ValueType {
    Null,
    Bool,
    Int,
    String,
    List,
    Object
};

struct TypedValue {
    ValueType type{ValueType::Null};
    bool bool_val{false};
    int64_t int_val{0};
    std::string str_val{};
    std::vector<TypedValue> list_val{};
    std::map<std::string, TypedValue> obj_val{};

    TypedValue() : type(ValueType::Null) {}
    TypedValue(std::nullptr_t) : type(ValueType::Null) {}
    TypedValue(bool b) : type(ValueType::Bool), bool_val(b) {}
    TypedValue(int i) : type(ValueType::Int), int_val(static_cast<int64_t>(i)) {}
    TypedValue(int64_t i) : type(ValueType::Int), int_val(i) {}
    TypedValue(uint64_t u) : type(ValueType::Int), int_val(static_cast<int64_t>(u)) {}
    TypedValue(const char* s) : type(ValueType::String), str_val(s ? s : "") {}
    TypedValue(const std::string& s) : type(ValueType::String), str_val(s) {}
    TypedValue(const std::vector<TypedValue>& l) : type(ValueType::List), list_val(l) {}
    TypedValue(const std::map<std::string, TypedValue>& o) : type(ValueType::Object), obj_val(o) {}

    bool is_null() const { return type == ValueType::Null; }
    bool is_bool() const { return type == ValueType::Bool; }
    bool is_int() const { return type == ValueType::Int; }
    bool is_string() const { return type == ValueType::String; }
    bool is_list() const { return type == ValueType::List; }
    bool is_object() const { return type == ValueType::Object; }

    bool as_bool() const {
        if (is_bool()) return bool_val;
        if (is_int()) return int_val != 0;
        return false;
    }

    int64_t as_int() const {
        if (is_int()) return int_val;
        if (is_bool()) return bool_val ? 1 : 0;
        return 0;
    }

    std::string as_string() const {
        if (is_string()) return str_val;
        if (is_null()) return "";
        return to_canonical_json();
    }

    bool has_key(const std::string& key) const {
        if (!is_object()) return false;
        return obj_val.find(key) != obj_val.end();
    }

    TypedValue get(const std::string& key, const TypedValue& default_val = TypedValue()) const {
        if (!is_object()) return default_val;
        auto it = obj_val.find(key);
        if (it != obj_val.end()) return it->second;
        return default_val;
    }

    TypedValue& operator[](const std::string& key) {
        if (type == ValueType::Null) {
            type = ValueType::Object;
        }
        return obj_val[key];
    }

    const TypedValue& operator[](const std::string& key) const {
        auto it = obj_val.find(key);
        if (it == obj_val.end()) {
            static const TypedValue null_val;
            return null_val;
        }
        return it->second;
    }

    bool operator==(const TypedValue& other) const {
        if (type != other.type) {
            // Permit int vs float/bool if needed, otherwise strict
            return false;
        }
        switch (type) {
            case ValueType::Null: return true;
            case ValueType::Bool: return bool_val == other.bool_val;
            case ValueType::Int: return int_val == other.int_val;
            case ValueType::String: return str_val == other.str_val;
            case ValueType::List: return list_val == other.list_val;
            case ValueType::Object: return obj_val == other.obj_val;
        }
        return false;
    }

    bool operator!=(const TypedValue& other) const {
        return !(*this == other);
    }

    std::string to_canonical_json() const;
    static TypedValue parse_json(const std::string& src);
};

// Cryptographic SHA-256 function
std::string sha256_hex(const std::string& input);

// Canonical JSON serializer matching Python:
// json.dumps(val, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
std::string to_canonical_json(const TypedValue& val);

// Guard Operations
enum class GuardOp {
    ALWAYS,
    EXISTS,
    NOT_EXISTS,
    EQ,
    NE,
    GT,
    GTE,
    LT,
    LTE
};

GuardOp parse_guard_op(const std::string& op_str);

// Mutation Operations
enum class MutationOp {
    NOOP,
    SET,
    ADD,
    SUB,
    DELETE
};

MutationOp parse_mutation_op(const std::string& op_str);

// Successor Kinds
enum class SuccessorKind {
    HALT,
    STATIC,
    PRESERVE
};

SuccessorKind parse_successor_kind(const std::string& kind_str);

struct Guard {
    GuardOp op{GuardOp::ALWAYS};
    std::string key{};
    TypedValue operand{};
};

struct Mutation {
    MutationOp op{MutationOp::NOOP};
    std::string key{};
    TypedValue operand{};
};

struct Successor {
    SuccessorKind kind{SuccessorKind::HALT};
    std::string value{};
};

struct Route {
    Guard guard{};
    std::vector<Mutation> mutations{};
    Successor successor{};
};

struct UoWContract {
    std::string identity{};
    std::vector<Route> routes{};
};

} // namespace uow_native
