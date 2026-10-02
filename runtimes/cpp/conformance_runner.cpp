#include "include/uow_native_protocol.hpp"

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;
using namespace uow_native;

static std::string read_file_string(const std::string& path) {
    std::ifstream in(path, std::ios::in | std::ios::binary);
    if (!in.is_open()) {
        throw std::runtime_error("Cannot open file: " + path);
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

static bool evaluate_vector_result(const TypedValue& actual, const TypedValue& expected, std::string& err_msg) {
    std::string actual_status = actual.get("status").as_string();
    std::string expected_status = expected.get("status").as_string();

    if (actual_status != expected_status) {
        err_msg = "Status mismatch: actual " + actual_status + " != expected " + expected_status;
        return false;
    }

    if (expected_status == "SUCCESS") {
        if (expected.has_key("ledger_length")) {
            if (actual.get("ledger_length").as_int() != expected.get("ledger_length").as_int()) {
                err_msg = "Ledger length mismatch";
                return false;
            }
            if (actual.get("ledger_integrity").as_bool() != expected.get("ledger_integrity").as_bool()) {
                err_msg = "Ledger integrity mismatch";
                return false;
            }
            // Check record hashes
            for (int i = 1; i <= 2; ++i) {
                std::string rec_key = "record_" + std::to_string(i);
                if (expected.has_key(rec_key)) {
                    std::string exp_h = expected.get(rec_key).get("record_hash").as_string();
                    std::string act_h = actual.get(rec_key).get("record_hash").as_string();
                    if (exp_h != act_h) {
                        err_msg = rec_key + " record_hash mismatch: actual " + act_h + " != expected " + exp_h;
                        return false;
                    }
                }
            }
            return true;
        }

        TypedValue exp_res = expected.get("result");
        TypedValue act_res = actual.get("result");

        if (exp_res.has_key("attributes")) {
            TypedValue exp_attrs = exp_res.get("attributes");
            TypedValue act_attrs = act_res.get("attributes");
            if (exp_attrs.is_object()) {
                for (const auto& [k, v] : exp_attrs.obj_val) {
                    if (!act_attrs.has_key(k) || act_attrs.get(k) != v) {
                        err_msg = "Attribute mismatch for key '" + k + "': actual " + act_attrs.get(k).to_canonical_json() + " != expected " + v.to_canonical_json();
                        return false;
                    }
                }
            }
        }

        if (exp_res.has_key("reserved_quantity")) {
            if (act_res.get("reserved_quantity").as_int() != exp_res.get("reserved_quantity").as_int()) {
                err_msg = "Reserved quantity mismatch";
                return false;
            }
            if (act_res.get("sku").as_string() != exp_res.get("sku").as_string()) {
                err_msg = "SKU mismatch";
                return false;
            }
        }
    } else {
        TypedValue exp_errors = expected.get("errors");
        TypedValue act_errors = actual.get("errors");

        if (!act_errors.is_list() || act_errors.list_val.empty()) {
            err_msg = "Expected errors but none returned";
            return false;
        }

        std::string exp_code = exp_errors.list_val[0].get("code").as_string();
        std::string act_code = act_errors.list_val[0].get("code").as_string();
        if (exp_code != act_code) {
            err_msg = "Error code mismatch: actual " + act_code + " != expected " + exp_code;
            return false;
        }
    }

    return true;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: conformance_runner [--all <vectors_dir>] | [<vector_file_path>] | [--stdin]" << std::endl;
        return 1;
    }

    std::string arg1 = argv[1];

    if (arg1 == "--all") {
        std::string dir_path = (argc >= 3) ? argv[2] : "conformance/vectors";
        std::vector<fs::path> files;
        for (const auto& entry : fs::directory_iterator(dir_path)) {
            if (entry.path().extension() == ".json") {
                files.push_back(entry.path());
            }
        }
        std::sort(files.begin(), files.end());

        int passed = 0;
        int failed = 0;

        for (const auto& p : files) {
            std::string stem = p.stem().string();
            std::string prefix = stem.substr(0, 3);

            NativeProtocolExecutor executor;
            try {
                std::string content = read_file_string(p.string());
                TypedValue vector_json = TypedValue::parse_json(content);
                TypedValue actual = executor.dispatch_vector(vector_json);
                TypedValue expected = vector_json.get("expected");

                std::string err_msg;
                bool ok = evaluate_vector_result(actual, expected, err_msg);

                if (ok) {
                    std::cout << prefix << " PASS" << std::endl;
                    passed++;
                } else {
                    std::cout << prefix << " FAIL: " << err_msg << std::endl;
                    failed++;
                }
            } catch (const std::exception& e) {
                std::cout << prefix << " ERROR: " << e.what() << std::endl;
                failed++;
            }
        }

        std::cout << std::endl;
        std::cout << "C++ semantic conformance: " << passed << "/" << (passed + failed) << std::endl;
        return failed == 0 ? 0 : 2;
    }

    // Single vector mode
    std::string json_content;
    if (arg1 == "--stdin") {
        std::ostringstream ss;
        ss << std::cin.rdbuf();
        json_content = ss.str();
    } else {
        json_content = read_file_string(arg1);
    }

    NativeProtocolExecutor executor;
    TypedValue vector_json = TypedValue::parse_json(json_content);
    TypedValue actual = executor.dispatch_vector(vector_json);

    std::cout << actual.to_canonical_json() << std::endl;
    return 0;
}
