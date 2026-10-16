import json

with open("artifacts/uow_native_3/c2_ablation_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

header = f"{'Condition':<24} | {'Valid JSON':<12} | {'Exact Disp':<12} | {'Unsafe YES':<12}"
print(header)
print("-" * len(header))

for name, spec in data["conditions"].items():
    cnt = spec["counts"]
    vj = cnt["valid_json"]
    ed = cnt["exact_disposition"]
    uy = cnt["unsafe_yes"]
    print(f"{name:<24} | {vj}/20 ({vj/20*100:.1f}%) | {ed}/20 ({ed/20*100:.1f}%) | {uy}/20 ({uy/20*100:.1f}%)")
