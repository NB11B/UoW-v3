#include "uow_embedded.hpp"

#include <iostream>
#include <string>
#include <vector>

using namespace uow_embedded;

static std::string state_canonical() {
    return "r0=10;r1=2;pc=3;sequence=4;halted=0";
}

static std::string proposal_canonical() {
    const std::string a(64, 'a');
    const std::string b(64, 'b');
    return "pre=" + a + ";post=" + b + ";pc=3;halted=0";
}

static std::string certificate_canonical() {
    const std::string c(64, 'c');
    return "proposal=" + c + ";valid=1;reason=0";
}

static std::string evidence_canonical() {
    const std::string a(64, 'a');
    const std::string b(64, 'b');
    const std::string c(64, 'c');
    const std::string d(64, 'd');
    const std::string e(64, 'e');
    return "step=5;pre=" + a + ";post=" + b + ";proposal=" + c +
        ";certificate=" + d + ";prev=" + e;
}

static std::string vote_canonical() {
    const std::string a(64, 'a');
    const std::string b(64, 'b');
    const std::string c(64, 'c');
    const std::string d(64, 'd');
    const std::string e(64, 'e');
    return "{\"accepted\":true"
        ",\"certificate_hash\":\"" + d + "\""
        ",\"evidence_step\":5"
        ",\"node_id\":\"authority_a_esp32\""
        ",\"pre_evidence_root\":\"" + e + "\""
        ",\"pre_state_hash\":\"" + a + "\""
        ",\"proposal_hash\":\"" + c + "\""
        ",\"proposed_state_hash\":\"" + b + "\""
        ",\"rejection_reason\":null"
        ",\"ruleset_version\":\"uow-authority-v1\"}";
}

static std::string qc_canonical() {
    const std::string a(64, 'a');
    const std::string b(64, 'b');
    const std::string c(64, 'c');
    const std::string d(64, 'd');
    const std::string e(64, 'e');
    const std::string f(64, 'f');
    const std::string g(64, '1');
    const std::string h(64, '2');
    return "{\"certificate_hash\":\"" + d + "\""
        ",\"committed_state_hash\":\"" + b + "\""
        ",\"evidence_step\":5"
        ",\"expected_evidence_root\":\"" + f + "\""
        ",\"pre_evidence_root\":\"" + e + "\""
        ",\"pre_state_hash\":\"" + a + "\""
        ",\"proposal_hash\":\"" + c + "\""
        ",\"proposed_state_hash\":\"" + b + "\""
        ",\"ruleset_version\":\"uow-authority-v1\""
        ",\"threshold\":2"
        ",\"uow_id\":\"test_uow\""
        ",\"vote_hashes\":[\"" + g + "\",\"" + h + "\"]"
        ",\"voters\":[\"authority_a_esp32\",\"authority_b_unoq_stm32\"]}";
}

int main(int argc, char** argv) {
    if (argc < 2) return 3;
    const std::string mode = argv[1];
    std::string canonical;
    if (mode == "state") canonical = state_canonical();
    else if (mode == "proposal") canonical = proposal_canonical();
    else if (mode == "certificate") canonical = certificate_canonical();
    else if (mode == "evidence") canonical = evidence_canonical();
    else if (mode == "vote") canonical = vote_canonical();
    else if (mode == "qc") canonical = qc_canonical();
    else return 3;

    std::cout << canonical << "\n";
    std::cout << hex_digest(sha256(canonical)) << "\n";
    return 0;
}
