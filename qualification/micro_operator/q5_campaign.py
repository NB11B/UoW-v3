"""Frozen Q5 portable acceptance suite."""
import json
import statistics
import time
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q5_group_certificate import GroupAuthority
from qualification.micro_operator.q4_grouped import reference

def run():
    gates={}
    seq=tuple((i*11//7)%2 for i in range(96))
    a,_=make_cluster(); b,_=make_cluster()
    normal=reference(a,seq)
    status,cert=GroupAuthority(b).commit(seq)
    gates["01_group_success"]=status=="COMMITTED" and cert is not None
    gates["02_state_evidence_equivalence"]=(
        all(a.nodes[k].state.state_hash==b.nodes[k].state.state_hash and
            a.nodes[k].ledger.root_hash()==b.nodes[k].ledger.root_hash() for k in a.nodes))
    gates["03_member_audit"]=len(cert.members)==len(seq) and len(set(cert.members))==len(seq)
    c,_=make_cluster(); group=GroupAuthority(c)
    status,_=group.commit([1,0,1],interrupt=True)
    gates["04_interrupt_no_mutation"]=status=="INTERRUPTED_PREPUBLISH" and all(n.state.sequence==0 for n in c.nodes.values())
    c,_=make_cluster();c.network.isolate_node("B");c.network.isolate_node("C")
    status,_=GroupAuthority(c).commit([1,0])
    gates["05_no_quorum"]=status=="NO_QUORUM" and all(n.state.sequence==0 for n in c.nodes.values())
    c,_=make_cluster();g=GroupAuthority(c)
    g.commit([1,0]); old=c.nodes["A"].state.state_hash
    status,_=g.commit([1,0])
    gates["06_group_prestate_bound"]=status=="COMMITTED" and c.nodes["A"].state.state_hash!=old
    c,_=make_cluster()
    for invalid in ([],[True],[2],[0]*257):
        try: GroupAuthority(c).commit(invalid)
        except ValueError: pass
        else: raise AssertionError("invalid group accepted")
    gates["07_invalid_fail_closed"]=all(n.state.sequence==0 for n in c.nodes.values())
    c,_=make_cluster()
    c.nodes["C"].state=c.nodes["C"].state.with_attribute("counter",999)
    status,_=GroupAuthority(c).commit([1,0])
    gates["08_divergence_fail_closed"]=status=="DIVERGED" and all(n.state.sequence==0 for n in (c.nodes["A"],c.nodes["B"]))
    samples={"baseline":[],"group":[]}
    for i in range(5):
        for arm in (("group","baseline") if i%2 else ("baseline","group")):
            c,_=make_cluster(); t=time.perf_counter()
            if arm=="group":GroupAuthority(c).commit(seq)
            else:reference(c,seq)
            samples[arm].append((time.perf_counter()-t)*1000)
    result={"campaign":"Q5-portable-group-certificate","gates":gates,
            "passed":all(gates.values()),"examples":len(seq),
            "reference_median_ms":statistics.median(samples["baseline"]),
            "group_median_ms":statistics.median(samples["group"]),
            "physical_atomicity":False,"durable_atomicity":False,
            "native_member_evidence":True,"quorum_group_votes":3}
    result["speedup"]=result["reference_median_ms"]/result["group_median_ms"]
    return result

if __name__=="__main__":
    outcome=run();print(json.dumps(outcome,indent=2,sort_keys=True))
    if not outcome["passed"]:raise SystemExit(1)
