#include "uow_embedded.hpp"

#include <iostream>
#include <string>

using namespace uow_embedded;

static void print_state(const State& s, const EvidenceLedger& ledger) {
    std::cout
        << "{"
        << "\"r0\":" << s.r0 << ","
        << "\"r1\":" << s.r1 << ","
        << "\"pc\":" << s.pc << ","
        << "\"sequence\":" << s.sequence << ","
        << "\"halted\":" << (s.halted ? "true" : "false") << ","
        << "\"evidence_steps\":" << ledger.size() << ","
        << "\"evidence_valid\":" << (ledger.verify() ? "true" : "false")
        << "}" << std::endl;
}

int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "transfer";
    Program program = Program::transfer_r0_to_r1();
    LocalClock proposer_clock{0, 7, false};
    LocalClock authority_clock{1000, 13, false};
    EvidenceLedger ledger{true};

    if (mode == "transfer") {
        State state{};
        state.r0 = 5;
        state.r1 = 3;
        state.pc = 0;
        state.sequence = 0;
        state.halted = false;

        for (int i = 0; i < 100 && !state.halted; ++i) {
            auto result = execute_one(
                program, state, proposer_clock, authority_clock, ledger, FaultMode::NONE
            );
            if (!result.committed) {
                std::cerr << "unexpected rejection:" << reject_reason_string(result.certificate.reason);
                return 2;
            }
            state = result.state;
        }
        print_state(state, ledger);
        return 0;
    }

    State state{};
    state.r0 = 2;
    state.r1 = 1;
    state.pc = 0;
    state.sequence = 0;
    state.halted = false;

    FaultMode fault = FaultMode::NONE;
    if (mode == "tamper_state") fault = FaultMode::TAMPER_STATE;
    else if (mode == "tamper_prehash") fault = FaultMode::TAMPER_PREHASH;
    else if (mode == "tamper_route") fault = FaultMode::TAMPER_ROUTE;
    else return 3;

    auto result = execute_one(program, state, proposer_clock, authority_clock, ledger, fault);
    std::cout
        << "{"
        << "\"committed\":" << (result.committed ? "true" : "false") << ","
        << "\"reason\":\"" << reject_reason_string(result.certificate.reason) << "\","
        << "\"r0\":" << result.state.r0 << ","
        << "\"r1\":" << result.state.r1 << ","
        << "\"sequence\":" << result.state.sequence << ","
        << "\"evidence_steps\":" << ledger.size()
        << "}" << std::endl;
    return 0;
}
