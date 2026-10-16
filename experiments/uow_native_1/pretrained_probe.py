"""Frozen causal-LM neuron ablation test; optional torch/transformers dependency."""
import argparse, json, random
from contextlib import contextmanager
import torch

TEMPLATES = [
    "Which number is larger: {a} or {b}? Answer with the number only.",
    "Select the maximum of {a} and {b}. Reply with its numeral.",
    "A comparison of {a} versus {b}: give only the greater value.",
]

def rows(seed, count, template):
    rng = random.Random(seed)
    seen, result = set(), []
    while len(result) < count:
        lo, hi = sorted(rng.sample(range(10,95), 2))
        a,b = (hi,lo) if len(result)%2 == 0 else (lo,hi)
        if (a,b) in seen: continue
        seen.add((a,b))
        result.append((TEMPLATES[template].format(a=a,b=b),str(hi),str(lo)))
    return result

def independent_splits(seed, sizes=(24, 48, 48)):
    """Disjoint unordered numeric pairs, even across prompt-template shifts."""
    rng = random.Random(seed)
    universe = [(a, b) for a in range(10, 95) for b in range(a + 1, 95)]
    if sum(sizes) > len(universe):
        raise ValueError("Requested more distinct pairs than available")
    rng.shuffle(universe)
    out = []
    offset = 0
    for template, count in enumerate(sizes):
        partition = []
        for j, (lo, hi) in enumerate(universe[offset:offset + count]):
            a, b = (hi, lo) if j % 2 == 0 else (lo, hi)
            partition.append((TEMPLATES[template].format(a=a, b=b), str(hi), str(lo)))
        out.append(partition)
        offset += count
    return tuple(out)


def rank_p_value(effect, controls):
    if not controls:
        raise ValueError("At least one control is required")
    return (1 + sum(value >= effect for value in controls)) / (1 + len(controls))


def projections(model):
    return [(n,m) for n,m in model.named_modules() if n.endswith("mlp.down_proj") and hasattr(m,"in_features")]

@contextmanager
def ablate(module, index):
    def hook(_, args):
        x=args[0].clone()
        x[...,index]=0
        return (x,*args[1:])
    handle=module.register_forward_pre_hook(hook)
    try: yield
    finally: handle.remove()

def measure(model, tokenizer, prompts, device, layer=None, neuron=None):
    correct=0
    total=0.
    for prompt, positive, negative in prompts:
        ids_pos=tokenizer.encode(positive,add_special_tokens=False)
        ids_neg=tokenizer.encode(negative,add_special_tokens=False)
        if len(ids_pos)!=1 or len(ids_neg)!=1:
            raise ValueError("Requires single-token numeric answers")
        x=tokenizer(prompt,return_tensors="pt").to(device)
        with torch.inference_mode():
            if layer is None:
                logits=model(**x).logits[0,-1]
            else:
                with ablate(layer,neuron):
                    logits=model(**x).logits[0,-1]
        margin=float((logits[ids_pos[0]]-logits[ids_neg[0]]).item())
        correct+=margin>0
        total+=margin
    return {"accuracy":correct/len(prompts),"margin":total/len(prompts)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="HuggingFaceTB/SmolLM2-135M-Instruct")
    p.add_argument("--revision",required=True)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--sizes",type=int,nargs=3,default=(24,48,48))
    p.add_argument("--candidates",type=int,default=32)
    p.add_argument("--output",default="pretrained_report.json")
    args=p.parse_args()
    if len(args.revision)<16: raise ValueError("Specify immutable model revision SHA")
    from transformers import AutoModelForCausalLM, AutoTokenizer
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device="cuda" if torch.cuda.is_available() else "cpu"
    tokenizer=AutoTokenizer.from_pretrained(args.model,revision=args.revision,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(args.model,revision=args.revision,trust_remote_code=False).to(device).eval()
    for param in model.parameters(): param.requires_grad_(False)
    layers=projections(model)
    if not layers: raise ValueError("Model has no supported mlp.down_proj")
    name,layer=layers[-1]
    selection, holdout, shifted = independent_splits(args.seed,tuple(args.sizes))
    rng=random.Random(args.seed+31337)
    candidate=sorted(rng.sample(range(layer.in_features),min(args.candidates,layer.in_features)))
    if len(candidate)<2: raise ValueError("Need at least two sampled neurons")
    train_base=measure(model,tokenizer,selection,device)
    deltas=[(abs(train_base["margin"]-measure(model,tokenizer,selection,device,layer,i)["margin"]),i) for i in candidate]
    selected=max(deltas,key=lambda t:(t[0],-t[1]))[1]
    baseline=measure(model,tokenizer,holdout,device)
    intervention=measure(model,tokenizer,holdout,device,layer,selected)
    shift_base=measure(model,tokenizer,shifted,device)
    shift_intervention=measure(model,tokenizer,shifted,device,layer,selected)
    effect=abs(baseline["margin"]-intervention["margin"])
    controls=[abs(baseline["margin"]-measure(model,tokenizer,holdout,device,layer,i)["margin"]) for i in candidate if i!=selected]
    p_value=rank_p_value(effect,controls)
    report={"campaign":"UOW-NATIVE-1 Stage 2","model":args.model,"revision":args.revision,
        "seed":args.seed,"sizes":args.sizes,"layer":name,"neuron":selected,"candidates":len(candidate),
        "selection_train_only":True,"baseline":baseline,"intervention":intervention,
        "shift_baseline":shift_base,"shift_intervention":shift_intervention,
        "holdout_margin_effect":effect,"random_control_margin_effects":controls,
        "control_rank_p":p_value,"exploratory_control_rank_below_0_05":p_value<0.05,
        "statistical_warning":"Selected and comparison neurons are not exchangeable; rank is descriptive, not a valid confirmatory p-value.",
        "limitations":"Neural intervention only; not UoW conformance or isolated capability."}
    result=json.dumps(report,indent=2,sort_keys=True)
    with open(args.output,"w",encoding="utf8") as file: file.write(result+"\n")
    print(result)

if __name__=="__main__": main()
