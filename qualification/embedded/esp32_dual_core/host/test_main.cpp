#include "uow_embedded.hpp"

#include <cassert>
#include <condition_variable>
#include <deque>
#include <iostream>
#include <mutex>
#include <random>
#include <string>
#include <thread>

using namespace uow_embedded;

template <typename T>
class BlockingQueue {
public:
    void push(const T& v) {
        std::lock_guard<std::mutex> lk(m_);
        q_.push_back(v);
        cv_.notify_one();
    }
    T pop() {
        std::unique_lock<std::mutex> lk(m_);
        cv_.wait(lk, [&]{ return !q_.empty(); });
        T v = q_.front(); q_.pop_front(); return v;
    }
private:
    std::mutex m_;
    std::condition_variable cv_;
    std::deque<T> q_;
};

struct WorkItem { State snapshot; FaultMode fault; bool stop{false}; };

static void test_sha256() {
    assert(hex_digest(sha256(std::string("abc"))) ==
           "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

static State run_direct(uint64_t r0, uint64_t r1, uint64_t pstride, uint64_t astride,
                        EvidenceLedger& ledger) {
    Program program = Program::transfer_r0_to_r1();
    State s{r0, r1, 0, 0, false};
    LocalClock pc{0,pstride,false}, ac{100000,astride,false};
    while (!s.halted) {
        auto step = execute_one(program, s, pc, ac, ledger);
        assert(step.committed);
        s = step.state;
    }
    return s;
}

static void test_reference_parity() {
    std::mt19937_64 rng(20260922);
    for (int i=0;i<500;++i) {
        const uint64_t r0 = rng()%100;
        const uint64_t r1 = rng()%500;
        EvidenceLedger ledger;
        State out = run_direct(r0,r1,1,7,ledger);
        assert(out.r0 == 0);
        assert(out.r1 == r0+r1);
        assert(out.sequence == 2*r0+2);
        assert(ledger.size() == out.sequence);
        assert(ledger.verify());
    }
}

static void test_fault_rejection() {
    Program program = Program::transfer_r0_to_r1();
    State s{5,2,0,0,false};
    LocalClock pc{0,3,false};
    for (auto f : {FaultMode::TAMPER_STATE, FaultMode::TAMPER_PREHASH, FaultMode::TAMPER_ROUTE}) {
        EvidenceLedger ledger;
        auto p = propose(program,s,pc,f);
        auto before = hash_state(s);
        auto result = commit(program,s,p,ledger);
        assert(!result.committed);
        assert(hash_state(result.state)==before);
        assert(ledger.size()==0);
    }
}

static void test_stale_rejection() {
    Program program = Program::transfer_r0_to_r1();
    State s{2,0,0,0,false};
    LocalClock pc{0,1,false};
    auto p = propose(program,s,pc);
    State advanced=s; advanced.sequence++;
    EvidenceLedger ledger;
    auto result=commit(program,advanced,p,ledger);
    assert(!result.committed);
    assert(result.certificate.reason==RejectReason::STALE_PRE_STATE);
}

static void test_clock_independence() {
    Program program = Program::transfer_r0_to_r1();
    std::mt19937_64 rng(77);
    std::string baseline_root;
    for (int i=0;i<250;++i) {
        EvidenceLedger ledger;
        State s{20,3,0,0,false};
        LocalClock pc{rng(), (rng()%1000)+1, false};
        LocalClock ac{rng(), (rng()%1000)+1, false};
        if ((i%17)==0) pc.frozen=true;
        if ((i%23)==0) ac.frozen=true;
        while (!s.halted) {
            auto r=execute_one(program,s,pc,ac,ledger);
            assert(r.committed);
            s=r.state;
        }
        assert(s.r0==0 && s.r1==23);
        assert(ledger.verify());
        const auto root=hex_digest(ledger.root());
        if (i==0) baseline_root=root;
        assert(root==baseline_root);
    }
}

static std::pair<State,std::string> run_threaded(bool invert_names) {
    Program program=Program::transfer_r0_to_r1();
    BlockingQueue<WorkItem> snapshots;
    BlockingQueue<Proposal> proposals;
    LocalClock proposer_clock{invert_names?9000u:10u, invert_names?17u:3u, false};
    LocalClock authority_clock{invert_names?10u:9000u, invert_names?3u:17u, false};
    EvidenceLedger ledger;
    State state{50,25,0,0,false};

    std::thread proposer([&]{
        while (true) {
            auto w=snapshots.pop();
            if (w.stop) break;
            proposer_clock.advance();
            proposals.push(propose(program,w.snapshot,proposer_clock,w.fault));
        }
    });

    while (!state.halted) {
        snapshots.push({state,FaultMode::NONE,false});
        Proposal p=proposals.pop();
        authority_clock.advance();
        auto r=commit(program,state,p,ledger);
        assert(r.committed);
        state=r.state;
    }
    snapshots.push({{},FaultMode::NONE,true});
    proposer.join();
    assert(ledger.verify());
    return {state,hex_digest(ledger.root())};
}

static void test_clock_metadata_not_authority_bearing() {
    Program program = Program::transfer_r0_to_r1();
    State s{7,4,0,0,false};
    LocalClock c1{1,1,false};
    LocalClock c2{999999,777,false};
    auto p1=propose(program,s,c1);
    auto p2=propose(program,s,c2);
    assert(p1.proposer_clock != p2.proposer_clock);
    assert(p1.proposal_hash == p2.proposal_hash);
    auto cert1=certify(program,s,p1);
    auto cert2=certify(program,s,p2);
    assert(cert1.valid && cert2.valid);
    assert(cert1.certificate_hash == cert2.certificate_hash);
}

static void test_root_only_bounded_evidence_mode() {
    Program program = Program::transfer_r0_to_r1();
    EvidenceLedger ledger(false);
    State s{100,0,0,0,false};
    LocalClock pc{0,1,false}, ac{0,1,false};
    while (!s.halted) {
        auto r=execute_one(program,s,pc,ac,ledger);
        assert(r.committed);
        s=r.state;
    }
    assert(ledger.size()==202);
    assert(ledger.records().empty());
    assert(ledger.verify());
    assert(hex_digest(ledger.root()) != std::string(64,'0'));
}

static void test_dual_context_inversion() {
    auto a=run_threaded(false);
    auto b=run_threaded(true);
    assert(a.first.r0==0 && a.first.r1==75);
    assert(b.first.r0==0 && b.first.r1==75);
    assert(a.first.sequence==b.first.sequence);
    assert(a.second==b.second);
}

int main() {
    test_sha256();
    test_reference_parity();
    test_fault_rejection();
    test_stale_rejection();
    test_clock_independence();
    test_clock_metadata_not_authority_bearing();
    test_root_only_bounded_evidence_mode();
    test_dual_context_inversion();
    std::cout << "UoW ESP32 dual-core host qualification: PASS\n";
    return 0;
}
