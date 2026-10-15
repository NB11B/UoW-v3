"""Q3 integrated classification and authority qualification."""
from qualification.micro_operator.q3_cooperation import run


def test_three_specialists_native_quorum_and_baselines():
    result=run()
    assert result['status']=='PASS'
    assert result['journal_verified']
    assert result['native_uow_commits']==13
    assert result['fusion_accuracy']>result['isolated_mean_accuracy']


def test_cached_feature_training_matches_uncached_reference_exactly():
    """Independent reference preserves arithmetic order and model weights."""
    import math
    from qualification.micro_operator.q3_cooperation import dataset, train, SEED
    rows=dataset(300,SEED)
    for channels in ((0,), (1,), (2,), (0,1,2)):
        weights=[0.0]*(1+2*len(channels))
        for _ in range(25):
            for label,views in rows:
                x=[1.0]+[float(v)-0.5 for j in channels for v in views[j]]
                score=max(-30,min(30,sum(a*b for a,b in zip(weights,x))))
                p=1/(1+math.exp(-score))
                weights=[w+0.08*(label-p)*v for w,v in zip(weights,x)]
        assert train(rows,channels)==tuple(round(w,8) for w in weights)
