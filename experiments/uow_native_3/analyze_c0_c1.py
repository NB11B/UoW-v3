import json

with open("artifacts/uow_native_3/c0_c1_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

models = list(data["models"].keys())
cases = [c["example_id"] for c in data["models"]["H3_full"]["case_records"]]

header = f"{'Case':<32} " + " ".join(f"{m:<10}" for m in models) + " Expected"
print(header)
print("-" * len(header))

for i, cid in enumerate(cases):
    exp = data["models"]["H3_full"]["case_records"][i]["expected_disposition"]
    disps = " ".join(f"{data['models'][m]['case_records'][i]['certificate_disposition']:<10}" for m in models)
    print(f"{cid:<32} {disps} {exp}")
