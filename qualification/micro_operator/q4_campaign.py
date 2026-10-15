"""Single closed Q4 qualification campaign; no implicit protocol rewrites."""
import json
import statistics
import time
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q4_grouped import Plan, prepare, submit, reference, equivalent

def run():
    gates={}
    values=tuple((i*11//7)%2 for i in range(96))
    a,_=make_cluster(); b,_=make_cluster()
    x=reference(a, values); y=submit(b,prepare(b,values))
    gates["01_exact_history"]=x==y and len(y[1])==96 and equivalent(a,b)
    c,_=make_cluster()
    for invalid in ([], [3], [True], [1.0], [1]*257):
        try: prepare(c,invalid)
        except ValueError: pass
        else: raise AssertionError("preflight accepted invalid input")
    gates["02_reject_invalid_without_commit"]=len(c.journal)==0
    c,_=make_cluster(); p=prepare(c,[1,0,1])
    try: submit(c,Plan((0,0,1),p.base,p.digest))
    except ValueError: pass
    else: raise AssertionError("tamper accepted")
    gates["03_tamper_no_commit"]=not c.journal
    c,_=make_cluster();p=prepare(c,[1,0,1])
    first=submit(c,p);before=c.journal_root();second=submit(c,p)
    gates["04_replay_no_commit"]=first[0]=="COMPLETE" and second[0]=="STALE" and c.journal_root()==before
    c,_=make_cluster();p=prepare(c,[1,0,1,0]);part=submit(c,p,stop_after=2)
    d,_=make_cluster();reference(d,[1,0])
    gates["05_interruption_prefix"]=part[0]=="INTERRUPTED" and len(part[1])==2 and equivalent(c,d)
    c,_=make_cluster();c.network.isolate_node("B");c.network.isolate_node("C")
    refused=submit(c,prepare(c,[1,0]))
    gates["06_no_quorum_no_commit"]=refused[0]=="NO_QUORUM" and not c.journal
    c,heal=make_cluster();c.network.isolate_node("C")
    result=submit(c,prepare(c,[1,0,1]))
    c.network.restore_link("A","C");c.network.restore_link("B","C")
    repaired=heal.heal_node("C")
    gates["07_partition_recovery"]=result[0]=="COMPLETE" and repaired.success and len({n.state.state_hash for n in c.nodes.values()})==1
    a,_=make_cluster();b,_=make_cluster()
    clocks=[n.clock_ticks for n in b.nodes.values()]
    reference(a,values);submit(b,prepare(b,values))
    gates["08_clock_independence"]=len(set(clocks))>1 and equivalent(a,b)
    timings={"reference":[],"grouped":[]}
    for trial in range(7):
        order=("grouped","reference") if trial%2 else ("reference","grouped")
        for arm in order:
            cluster,_=make_cluster();started=time.perf_counter()
            if arm=="reference": reference(cluster,values)
            else: submit(cluster,prepare(cluster,values))
            timings[arm].append((time.perf_counter()-started)*1000)
    result={"campaign":"Q4-closed-v1","gates":gates,"passed":all(gates.values()),
            "items":len(values),"repeats":7,"per_item_certificates":True,
            "group_atomic":False,"physical_transport_qualified":False,
            "reference_median_ms":statistics.median(timings["reference"]),
            "grouped_median_ms":statistics.median(timings["grouped"])}
    result["speedup"]=result["reference_median_ms"]/result["grouped_median_ms"]
    return result

if __name__=="__main__":
    report=run();print(json.dumps(report,indent=2,sort_keys=True))
    if not report["passed"]:raise SystemExit(1)
