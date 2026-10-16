"""Synthetic native-neuron ablation pilot; not a Goodfire replication."""
import argparse
import json
import random
from dataclasses import asdict, dataclass

import torch
from torch import nn


@dataclass
class Result:
    seed: int
    baseline_accuracy: float
    shifted_accuracy: float
    selected_unit: int
    selected_unit_ablation_drop: float
    median_control_drop: float
    prediction_change_rate: float
    denial_violations: int
    approved_correct_commits: int
    approved_total: int


class TinyRelationNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.hidden = nn.Linear(2, 12)
        self.act = nn.Tanh()
        self.head = nn.Linear(12, 2)

    def forward(self, x, mask_unit=None):
        h = self.act(self.hidden(x))
        if mask_unit is not None:
            mask = torch.ones(h.shape[-1], dtype=h.dtype, device=h.device)
            mask[mask_unit] = 0
            h = h * mask
        return self.head(h)


def examples(n, generator, lo=-1., hi=1.):
    a = (hi - lo) * torch.rand((n, 1), generator=generator) + lo
    b = (hi - lo) * torch.rand((n, 1), generator=generator) + lo
    x = torch.cat([a, b], dim=1)
    y = (a[:, 0] > b[:, 0]).long()
    return x, y


def accuracy(model, x, y, ablate=None):
    with torch.no_grad():
        p = model(x, ablate).argmax(1)
    return float((p == y).float().mean()), p


def execute_proposal(prediction, authority, current_epoch, proposal_epoch):
    """Independent fail-closed authorization; predictions never carry authority."""
    return bool(authority and current_epoch == proposal_epoch and prediction == 1)


def run_seed(seed, train_n=1500, test_n=400, steps=250):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    gen = torch.Generator().manual_seed(seed + 9000)
    x_train, y_train = examples(train_n, gen)
    x_test, y_test = examples(test_n, gen)
    x_shift, y_shift = examples(test_n, gen, 0.5, 2.5)
    model = TinyRelationNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    for _ in range(steps):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(model(x_train), y_train)
        loss.backward()
        optimizer.step()
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    base, base_pred = accuracy(model, x_test, y_test)
    shift, _ = accuracy(model, x_shift, y_shift)
    interventions = []
    for unit in range(12):
        a, p = accuracy(model, x_test, y_test, unit)
        interventions.append((base - a, unit, float((p != base_pred).float().mean())))
    # Unit selection uses train examples only, never the held-out test set.
    train_base, _ = accuracy(model, x_train, y_train)
    selection = [(train_base - accuracy(model, x_train, y_train, u)[0], u) for u in range(12)]
    selected = max(selection, key=lambda z: (z[0], -z[1]))[1]
    selected_drop, _, changed = interventions[selected]
    controls = sorted(v[0] for v in interventions if v[1] != selected)
    median_control = controls[len(controls) // 2]
    denials = 0
    approved_correct = 0
    approved_total = 0
    for p, y in zip(base_pred.tolist(), y_test.tolist()):
        for authority, epoch in ((False, 7), (True, 6)):
            if execute_proposal(p, authority, 7, epoch):
                denials += 1
        if p == 1:
            approved_total += 1
            approved_correct += int(execute_proposal(p, True, 7, 7) and y == 1)
    return Result(seed, base, shift, selected, selected_drop, median_control,
                  changed, denials, approved_correct, approved_total)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=3)
    parser.add_argument('--output', default='')
    args = parser.parse_args()
    results = [asdict(run_seed(s)) for s in range(args.seeds)]
    report = {'campaign': 'UOW-NATIVE-1', 'scope': 'synthetic trained toy MLP; no LLM circuit claim',
              'results': results,
              'summary': {'all_denied_violations_zero': all(r['denial_violations'] == 0 for r in results),
                          'mean_baseline_accuracy': sum(r['baseline_accuracy'] for r in results)/len(results),
                          'mean_shifted_accuracy': sum(r['shifted_accuracy'] for r in results)/len(results),
                          'causal_ablation_exceeds_median_control': sum(r['selected_unit_ablation_drop'] > r['median_control_drop'] for r in results)}}
    out = json.dumps(report, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf8') as f:
            f.write(out + '\n')
    print(out)


if __name__ == '__main__':
    main()
