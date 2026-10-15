"""Q3: independent specialists, deterministic fusion, and real UoW authority.

Synthetic fixed-seed classification. Same training samples and raw information
for central and distributed models. No physical transport or energy claims.
"""
from __future__ import annotations
import json
import math
import random
import statistics
import time
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q2_campaign import work_for, FrozenMicroOperator
from uow.engine import propose

SEED=20261015

def dataset(count, seed):
    rng=random.Random(seed)
    rows=[]
    for _ in range(count):
        label=rng.randrange(2)
        views=[]
        for j in range(3):
            a=label ^ int(rng.random()<0.19+0.02*j)
            b=label ^ int(rng.random()<0.34+0.01*j)
            views.append((a,b))
        rows.append((label,tuple(views)))
    return rows

def train(rows,channels):
    weights=[0.0]*(1+2*len(channels))
    for _ in range(25):
        for label,views in rows:
            x=[1.0]+[float(v)-0.5 for j in channels for v in views[j]]
            score=max(-30,min(30,sum(a*b for a,b in zip(weights,x))))
            p=1/(1+math.exp(-score))
            weights=[w+0.08*(label-p)*v for w,v in zip(weights,x)]
    return tuple(round(x,8) for x in weights)

def predict(weights,views,channels):
    x=[1.0]+[float(v)-0.5 for j in channels for v in views[j]]
    return int(sum(a*b for a,b in zip(weights,x))>=0)

def run():
    training=dataset(6000,SEED)
    heldout=dataset(3000,SEED+1)
    specialists=[train(training,(j,)) for j in range(3)]
    centralized=train(training,(0,1,2))
    labels=[y for y,_ in heldout]
    local=[[predict(specialists[j],v,(j,)) for _,v in heldout] for j in range(3)]
    fusion=[int(sum(local[j][i] for j in range(3))>=2) for i in range(len(heldout))]
    central=[predict(centralized,v,(0,1,2)) for _,v in heldout]
    acc=lambda output:sum(a==b for a,b in zip(labels,output))/len(labels)
    local_acc=[acc(o) for o in local]
    assert acc(fusion)>statistics.mean(local_acc)+0.04
    assert abs(acc(fusion)-acc(central))<0.04

    # Qualify one learned multi-specialist decision as a real native UoW commit.
    # The classifier/fusion has no signing authority or direct commit capability.
    cluster,healer=make_cluster()
    model=FrozenMicroOperator((1,1,1),"q3-majority-frozen-v1")
    votes=fusion[:12]
    certs=[]
    for v in votes:
        # Encode only the already validated fused decision as a bounded UoW
        # using Q2's existing native contract constructor.
        work=work_for(model,100 if v else 0,100 if v else 0)
        proposal=propose(work,cluster.nodes["A"].state)
        result=cluster.submit(work,proposal)
        assert result.committed and result.quorum_certificate is not None
        certs.append(result.quorum_certificate.qc_hash)
    assert cluster.verify_journal()
    assert len({n.state.state_hash for n in cluster.nodes.values()})==1
    assert len({n.ledger.root_hash() for n in cluster.nodes.values()})==1

    # Reject stale proposal without mutating history.
    work=work_for(model,100,100)
    stale=propose(work,cluster.nodes["A"].state)
    assert cluster.submit(work,stale).committed
    before=len(cluster.journal)
    replay=cluster.submit(work,stale)
    assert not replay.committed and len(cluster.journal)==before

    # Specialist failure: surviving disagreement must produce abstention.
    fault=[]
    for j in range(3):
        two=[k for k in range(3) if k!=j]
        accepted=[i for i in range(len(labels)) if local[two[0]][i]==local[two[1]][i]]
        coverage=len(accepted)/len(labels)
        quality=sum(local[two[0]][i]==labels[i] for i in accepted)/len(accepted)
        fault.append({"failed":j,"coverage":coverage,"accuracy_at_coverage":quality})
        assert 0.5<coverage<0.85 and quality>0.90

    return {"status":"PASS","seed":SEED,"train":len(training),"heldout":len(heldout),
            "individual_accuracy":local_acc,"isolated_mean_accuracy":statistics.mean(local_acc),
            "fusion_accuracy":acc(fusion),"central_accuracy":acc(central),
            "parameters":{"specialists_total":sum(map(len,specialists)),
                          "central":len(centralized)},
            "native_uow_commits":len(certs)+1,"journal_verified":True,
            "faults":fault,
            "limits":["synthetic only","in-process UoW authority","no physical transport",
                      "no energy claim","no independently attested model weights"]}

if __name__=="__main__":
    print(json.dumps(run(),indent=2))
