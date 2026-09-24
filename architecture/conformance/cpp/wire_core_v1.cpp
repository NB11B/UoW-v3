#include <cctype>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> out;
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, delim)) out.push_back(item);
    return out;
}

static std::map<std::string, std::string> parse_wire(
    const std::string& line,
    std::string& kind
) {
    auto parts = split(line, '|');
    if (parts.size() < 3 || parts[0] != "UOW1") {
        throw std::runtime_error("INVALID_PREFIX");
    }
    kind = parts[1];
    if (
        kind != "STATE" &&
        kind != "PROPOSAL" &&
        kind != "CERTIFICATE" &&
        kind != "EVIDENCE"
    ) {
        throw std::runtime_error("UNKNOWN_KIND");
    }
    std::map<std::string, std::string> fields;
    for (size_t i = 2; i < parts.size(); ++i) {
        auto pos = parts[i].find('=');
        if (pos == std::string::npos) throw std::runtime_error("MALFORMED_FIELD");
        auto key = parts[i].substr(0, pos);
        auto value = parts[i].substr(pos + 1);
        if (fields.count(key)) throw std::runtime_error("DUPLICATE_FIELD");
        fields[key] = value;
    }
    return fields;
}

static std::string q(const std::string& s) {
    return std::string("\"") + s + "\"";
}

static void require(
    const std::map<std::string, std::string>& f,
    const std::vector<std::string>& keys
) {
    if (f.size() != keys.size()) throw std::runtime_error("FIELD_COUNT");
    for (const auto& k : keys) {
        if (!f.count(k)) throw std::runtime_error("MISSING_FIELD");
    }
}

static bool is_uint(const std::string& s) {
    if (s.empty()) return false;
    for (char c : s) {
        if (!std::isdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

static bool is_bool(const std::string& s) {
    return s == "0" || s == "1";
}

static bool is_hex64(const std::string& s) {
    if (s.size() != 64) return false;
    for (char c : s) {
        if (!std::isxdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

static void require_uint(
    const std::map<std::string,std::string>& f,
    const std::string& key
) {
    if (!is_uint(f.at(key))) throw std::runtime_error("INVALID_UINT");
}

static void require_bool(
    const std::map<std::string,std::string>& f,
    const std::string& key
) {
    if (!is_bool(f.at(key))) throw std::runtime_error("INVALID_BOOL");
}

static void require_hex64(
    const std::map<std::string,std::string>& f,
    const std::string& key
) {
    if (!is_hex64(f.at(key))) throw std::runtime_error("INVALID_HEX64");
}

static void validate_fields(
    const std::string& kind,
    const std::map<std::string,std::string>& f
) {
    if (kind == "STATE") {
        require(f, {"r0","r1","pc","sequence","halted"});
        for (const auto& k : {"r0","r1","pc","sequence"}) require_uint(f, k);
        require_bool(f, "halted");
        return;
    }
    if (kind == "PROPOSAL") {
        require(f, {
            "pre_state_hash","proposal_hash","r0","r1","pc","sequence",
            "halted","selected_pc","proposal_halted","proposer_clock"
        });
        require_hex64(f, "pre_state_hash");
        require_hex64(f, "proposal_hash");
        for (const auto& k : {"r0","r1","pc","sequence","selected_pc","proposer_clock"}) {
            require_uint(f, k);
        }
        require_bool(f, "halted");
        require_bool(f, "proposal_halted");
        return;
    }
    if (kind == "CERTIFICATE") {
        require(f, {"valid","reason","certificate_hash"});
        require_bool(f, "valid");
        require_hex64(f, "certificate_hash");
        if (f.at("reason").empty()) throw std::runtime_error("INVALID_TOKEN");
        return;
    }
    if (kind == "EVIDENCE") {
        require(f, {
            "step","pre_state_hash","post_state_hash","proposal_hash",
            "certificate_hash","prev_record_hash","record_hash"
        });
        require_uint(f, "step");
        for (const auto& k : {
            "pre_state_hash","post_state_hash","proposal_hash",
            "certificate_hash","prev_record_hash","record_hash"
        }) {
            require_hex64(f, k);
        }
        return;
    }
    throw std::runtime_error("UNKNOWN_KIND");
}

static void emit_json(
    const std::string& kind,
    const std::map<std::string,std::string>& f
) {
    std::cout << "{\"kind\":" << q(kind);
    for (const auto& kv : f) {
        std::cout << ",\"" << kv.first << "\":" << q(kv.second);
    }
    std::cout << "}" << std::endl;
}

static std::string sample(const std::string& kind) {
    const std::string a(64, 'a');
    const std::string b(64, 'b');
    const std::string c(64, 'c');
    const std::string d(64, 'd');
    if (kind == "STATE") {
        return "UOW1|STATE|r0=5|r1=3|pc=2|sequence=7|halted=0";
    }
    if (kind == "PROPOSAL") {
        return "UOW1|PROPOSAL|pre_state_hash="+a+"|proposal_hash="+b+
            "|r0=4|r1=4|pc=3|sequence=7|halted=0|selected_pc=3|proposal_halted=0|proposer_clock=99";
    }
    if (kind == "CERTIFICATE") {
        return "UOW1|CERTIFICATE|valid=0|reason=STATE_DIVERGENCE|certificate_hash="+c;
    }
    if (kind == "EVIDENCE") {
        return "UOW1|EVIDENCE|step=8|pre_state_hash="+a+"|post_state_hash="+b+
            "|proposal_hash="+c+"|certificate_hash="+d+"|prev_record_hash="+a+"|record_hash="+b;
    }
    throw std::runtime_error("UNKNOWN_KIND");
}

int main(int argc, char** argv) {
    try {
        if (argc < 3) return 3;
        const std::string mode = argv[1];
        if (mode == "sample") {
            std::cout << sample(argv[2]) << std::endl;
            return 0;
        }
        if (mode != "decode") return 3;

        std::string kind;
        auto fields = parse_wire(argv[2], kind);
        validate_fields(kind, fields);
        emit_json(kind, fields);
        return 0;
    } catch (const std::exception& e) {
        std::cout << "{\"error\":" << q(e.what()) << "}" << std::endl;
        return 2;
    }
}
