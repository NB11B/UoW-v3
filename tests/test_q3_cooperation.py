"""Q3 integrated classification and authority qualification."""
from qualification.micro_operator.q3_cooperation import run


def test_three_specialists_native_quorum_and_baselines():
    result=run()
    assert result['status']=='PASS'
    assert result['journal_verified']
    assert result['native_uow_commits']==13
    assert result['fusion_accuracy']>result['isolated_mean_accuracy']
