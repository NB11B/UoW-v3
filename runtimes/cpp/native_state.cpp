#include "include/uow_native_state.hpp"

#include <cctype>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <cstring>

namespace uow_native {

namespace {

// Standard SHA-256 implementation
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

std::string encode_utf8(uint32_t cp) {
    std::string out;
    if (cp <= 0x7F) {
        out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
        out.push_back(static_cast<char>(0xC0 | ((cp >> 6) & 0x1F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
        out.push_back(static_cast<char>(0xE0 | ((cp >> 12) & 0x0F)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0x10FFFF) {
        out.push_back(static_cast<char>(0xF0 | ((cp >> 18) & 0x07)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
    return out;
}

} // namespace

std::string sha256_hex(const std::string& input) {
    const uint8_t* data = reinterpret_cast<const uint8_t*>(input.data());
    size_t len = input.size();

    std::array<uint32_t, 8> h = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
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

        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
        for (int i = 0; i < 64; ++i) {
            const uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            const uint32_t ch = (e & f) ^ ((~e) & g);
            const uint32_t temp1 = hh + S1 + ch + K[i] + w[i];
            const uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const uint32_t temp2 = S0 + maj;
            hh = g; g = f; f = e; e = d + temp1; d = c; c = b; b = a; a = temp1 + temp2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d;
        h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }

    std::ostringstream ss;
    for (uint32_t word : h) {
        ss << std::hex << std::setfill('0') << std::setw(8) << word;
    }
    return ss.str();
}

std::string TypedValue::to_canonical_json() const {
    switch (type) {
        case ValueType::Null:
            return "null";
        case ValueType::Bool:
            return bool_val ? "true" : "false";
        case ValueType::Int:
            return std::to_string(int_val);
        case ValueType::String: {
            std::ostringstream ss;
            ss << '"';
            for (unsigned char c : str_val) {
                switch (c) {
                    case '"':  ss << "\\\""; break;
                    case '\\': ss << "\\\\"; break;
                    case '\b': ss << "\\b"; break;
                    case '\f': ss << "\\f"; break;
                    case '\n': ss << "\\n"; break;
                    case '\r': ss << "\\r"; break;
                    case '\t': ss << "\\t"; break;
                    default:
                        if (c < 0x20) {
                            ss << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
                        } else {
                            ss << static_cast<char>(c);
                        }
                        break;
                }
            }
            ss << '"';
            return ss.str();
        }
        case ValueType::List: {
            std::ostringstream ss;
            ss << '[';
            for (size_t i = 0; i < list_val.size(); ++i) {
                if (i > 0) ss << ',';
                ss << list_val[i].to_canonical_json();
            }
            ss << ']';
            return ss.str();
        }
        case ValueType::Object: {
            std::ostringstream ss;
            ss << '{';
            size_t idx = 0;
            // std::map automatically iterates in sorted order of string keys
            for (const auto& [k, v] : obj_val) {
                if (idx++ > 0) ss << ',';
                // Escape key
                ss << '"';
                for (unsigned char c : k) {
                    if (c == '"') ss << "\\\"";
                    else if (c == '\\') ss << "\\\\";
                    else ss << static_cast<char>(c);
                }
                ss << "\":" << v.to_canonical_json();
            }
            ss << '}';
            return ss.str();
        }
    }
    return "null";
}

std::string to_canonical_json(const TypedValue& val) {
    return val.to_canonical_json();
}

// Lightweight recursive-descent JSON parser
class JsonParser {
public:
    explicit JsonParser(const std::string& src) : src_(src), pos_(0) {}

    TypedValue parse() {
        skip_ws();
        TypedValue val = parse_value();
        skip_ws();
        return val;
    }

private:
    const std::string& src_;
    size_t pos_{0};

    void skip_ws() {
        while (pos_ < src_.size() && (src_[pos_] == ' ' || src_[pos_] == '\t' || src_[pos_] == '\n' || src_[pos_] == '\r')) {
            ++pos_;
        }
    }

    char peek() const {
        return pos_ < src_.size() ? src_[pos_] : '\0';
    }

    char get() {
        return pos_ < src_.size() ? src_[pos_++] : '\0';
    }

    TypedValue parse_value() {
        skip_ws();
        char c = peek();
        if (c == 'n') return parse_null();
        if (c == 't' || c == 'f') return parse_bool();
        if (c == '"') return parse_string();
        if (c == '[') return parse_list();
        if (c == '{') return parse_object();
        if (c == '-' || (c >= '0' && c <= '9')) return parse_number();
        throw std::runtime_error(std::string("Unexpected JSON token at pos ") + std::to_string(pos_));
    }

    TypedValue parse_null() {
        if (src_.substr(pos_, 4) == "null") {
            pos_ += 4;
            return TypedValue(nullptr);
        }
        throw std::runtime_error("Malformed null");
    }

    TypedValue parse_bool() {
        if (src_.substr(pos_, 4) == "true") {
            pos_ += 4;
            return TypedValue(true);
        }
        if (src_.substr(pos_, 5) == "false") {
            pos_ += 5;
            return TypedValue(false);
        }
        throw std::runtime_error("Malformed bool");
    }

    TypedValue parse_number() {
        size_t start = pos_;
        if (peek() == '-') get();
        while (std::isdigit(static_cast<unsigned char>(peek()))) get();
        // Check if integer
        if (peek() != '.' && peek() != 'e' && peek() != 'E') {
            std::string num_str = src_.substr(start, pos_ - start);
            int64_t val = std::stoll(num_str);
            return TypedValue(val);
        }
        // Floating point if decimal point exists (still store integral part or as needed)
        if (peek() == '.') {
            get();
            while (std::isdigit(static_cast<unsigned char>(peek()))) get();
        }
        if (peek() == 'e' || peek() == 'E') {
            get();
            if (peek() == '+' || peek() == '-') get();
            while (std::isdigit(static_cast<unsigned char>(peek()))) get();
        }
        std::string num_str = src_.substr(start, pos_ - start);
        double d = std::stod(num_str);
        int64_t int_cast = static_cast<int64_t>(d);
        return TypedValue(int_cast);
    }

    TypedValue parse_string() {
        get(); // consume '"'
        std::string res;
        while (pos_ < src_.size()) {
            char c = get();
            if (c == '"') {
                return TypedValue(res);
            }
            if (c == '\\') {
                char esc = get();
                switch (esc) {
                    case '"': res.push_back('"'); break;
                    case '\\': res.push_back('\\'); break;
                    case '/': res.push_back('/'); break;
                    case 'b': res.push_back('\b'); break;
                    case 'f': res.push_back('\f'); break;
                    case 'n': res.push_back('\n'); break;
                    case 'r': res.push_back('\r'); break;
                    case 't': res.push_back('\t'); break;
                    case 'u': {
                        std::string hex_str = src_.substr(pos_, 4);
                        pos_ += 4;
                        uint32_t cp = static_cast<uint32_t>(std::stoul(hex_str, nullptr, 16));
                        // Check for UTF-16 surrogate pair
                        if (cp >= 0xD800 && cp <= 0xDBFF && pos_ + 6 <= src_.size() && src_[pos_] == '\\' && src_[pos_+1] == 'u') {
                            pos_ += 2;
                            std::string low_hex = src_.substr(pos_, 4);
                            pos_ += 4;
                            uint32_t low = static_cast<uint32_t>(std::stoul(low_hex, nullptr, 16));
                            if (low >= 0xDC00 && low <= 0xDFFF) {
                                cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                            }
                        }
                        res += encode_utf8(cp);
                        break;
                    }
                    default:
                        res.push_back(esc);
                        break;
                }
            } else {
                res.push_back(c);
            }
        }
        throw std::runtime_error("Unterminated string");
    }

    TypedValue parse_list() {
        get(); // consume '['
        std::vector<TypedValue> list;
        skip_ws();
        if (peek() == ']') {
            get();
            return TypedValue(list);
        }
        while (true) {
            list.push_back(parse_value());
            skip_ws();
            char c = get();
            if (c == ']') break;
            if (c != ',') throw std::runtime_error("Expected ',' in list");
        }
        return TypedValue(list);
    }

    TypedValue parse_object() {
        get(); // consume '{'
        std::map<std::string, TypedValue> obj;
        skip_ws();
        if (peek() == '}') {
            get();
            return TypedValue(obj);
        }
        while (true) {
            skip_ws();
            if (peek() != '"') throw std::runtime_error("Expected string key in object");
            TypedValue key_val = parse_string();
            std::string key = key_val.str_val;
            skip_ws();
            if (get() != ':') throw std::runtime_error("Expected ':' after object key");
            TypedValue val = parse_value();
            obj[key] = val;
            skip_ws();
            char c = get();
            if (c == '}') break;
            if (c != ',') throw std::runtime_error("Expected ',' in object");
        }
        return TypedValue(obj);
    }
};

TypedValue TypedValue::parse_json(const std::string& src) {
    JsonParser parser(src);
    return parser.parse();
}

GuardOp parse_guard_op(const std::string& op_str) {
    if (op_str == "ALWAYS") return GuardOp::ALWAYS;
    if (op_str == "EXISTS") return GuardOp::EXISTS;
    if (op_str == "NOT_EXISTS") return GuardOp::NOT_EXISTS;
    if (op_str == "EQ") return GuardOp::EQ;
    if (op_str == "NE") return GuardOp::NE;
    if (op_str == "GT") return GuardOp::GT;
    if (op_str == "GTE") return GuardOp::GTE;
    if (op_str == "LT") return GuardOp::LT;
    if (op_str == "LTE") return GuardOp::LTE;
    return GuardOp::ALWAYS;
}

MutationOp parse_mutation_op(const std::string& op_str) {
    if (op_str == "NOOP") return MutationOp::NOOP;
    if (op_str == "SET") return MutationOp::SET;
    if (op_str == "ADD") return MutationOp::ADD;
    if (op_str == "SUB") return MutationOp::SUB;
    if (op_str == "DELETE") return MutationOp::DELETE;
    return MutationOp::NOOP;
}

SuccessorKind parse_successor_kind(const std::string& kind_str) {
    if (kind_str == "HALT") return SuccessorKind::HALT;
    if (kind_str == "STATIC") return SuccessorKind::STATIC;
    if (kind_str == "PRESERVE") return SuccessorKind::PRESERVE;
    return SuccessorKind::HALT;
}

std::string NativeWorldState::compute_hash() const {
    TypedValue payload(std::map<std::string, TypedValue>{
        {"attributes", attributes},
        {"cursor", cursor},
        {"sequence", TypedValue(sequence)},
        {"status", TypedValue(status)}
    });
    std::string canonical = payload.to_canonical_json();
    return sha256_hex(canonical);
}

bool NativeWorldState::evaluate_guard(const Guard& guard) const {
    if (guard.op == GuardOp::ALWAYS) return true;
    if (guard.key.empty()) return true;

    bool exists = attributes.has_key(guard.key);
    if (guard.op == GuardOp::EXISTS) return exists;
    if (guard.op == GuardOp::NOT_EXISTS) return !exists;
    if (!exists) return false;

    TypedValue val = attributes[guard.key];
    if (guard.op == GuardOp::EQ) return val == guard.operand;
    if (guard.op == GuardOp::NE) return val != guard.operand;

    if (val.is_int() && guard.operand.is_int()) {
        int64_t v = val.as_int();
        int64_t op = guard.operand.as_int();
        if (guard.op == GuardOp::GT) return v > op;
        if (guard.op == GuardOp::GTE) return v >= op;
        if (guard.op == GuardOp::LT) return v < op;
        if (guard.op == GuardOp::LTE) return v <= op;
    }
    return false;
}

void NativeWorldState::apply_mutation(const Mutation& mutation) {
    if (mutation.op == MutationOp::NOOP || mutation.key.empty()) return;

    if (mutation.op == MutationOp::SET) {
        attributes[mutation.key] = mutation.operand;
    } else if (mutation.op == MutationOp::ADD) {
        int64_t current = attributes.get(mutation.key, TypedValue(0)).as_int();
        int64_t operand = mutation.operand.as_int();
        attributes[mutation.key] = TypedValue(current + operand);
    } else if (mutation.op == MutationOp::SUB) {
        int64_t current = attributes.get(mutation.key, TypedValue(0)).as_int();
        int64_t operand = mutation.operand.as_int();
        attributes[mutation.key] = TypedValue(current - operand);
    } else if (mutation.op == MutationOp::DELETE) {
        if (attributes.is_object()) {
            attributes.obj_val.erase(mutation.key);
        }
    }
}

NativeWorldState NativeWorldState::from_typed_value(const TypedValue& val) {
    NativeWorldState state;
    if (!val.is_object()) return state;

    state.attributes = val.get("attributes", TypedValue(std::map<std::string, TypedValue>{}));
    state.cursor = val.get("cursor", TypedValue(nullptr));
    state.status = val.get("status", TypedValue("RUNNING")).as_string();
    state.sequence = val.get("sequence", TypedValue(0)).as_int();
    return state;
}

TypedValue NativeWorldState::to_typed_value() const {
    return TypedValue(std::map<std::string, TypedValue>{
        {"attributes", attributes},
        {"cursor", cursor},
        {"sequence", TypedValue(sequence)},
        {"status", TypedValue(status)},
        {"state_hash", TypedValue(compute_hash())}
    });
}

} // namespace uow_native
