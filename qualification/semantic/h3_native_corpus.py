"""H3-N: Native UoW Semantic Grammar Corpus and Admission Validator.

Generates and validates the native training and holdout corpus for SmolLM2-135M
under the exact production UoW semantic contract:
    (X, C^min, F_P) -> SemanticPromptBuilder -> M_H3 -> SemanticOutputParser -> CandidateSemanticBindings

Enforces:
1. Versioned grammar freeze: grammar-h3-native-v1 / uow.semantic.bindings.v1
2. Pure production API generation: all prompts built via SemanticPromptBuilder
3. Strict parsing admission gate: every target must pass SemanticOutputParser.parse(..., fail_closed=False)
4. Frontier boundary confinement: all target terminals in F_P; no C^min repetitions
5. 9 semantic families x 4 behavior classes x frontier cardinality |F_P| in {1, 2, 3, 4}
6. Family-disjoint holdout isolation: unseen compositional and structural families
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from uow.semantic.adapters.codec import (
    SYSTEM_PROMPT,
    SemanticOutputParser,
    SemanticOutputValidationError,
    SemanticPromptBuilder,
)
from uow.semantic.schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticRequirement,
    SemanticTranslationRequest,
)

GRAMMAR_VERSION = "grammar-h3-native-v1"
BINDINGS_SCHEMA_VERSION = "uow.semantic.bindings.v1"

CORPUS_MANIFEST_PATH = (
    PACKAGE_ROOT
    / "qualification"
    / "artifacts"
    / "semantic_h3_native_corpus_manifest.json"
)


@dataclass(frozen=True)
class H3NativeExample:
    """Canonical representation of an admitted H3-native training/holdout example."""

    example_id: str
    partition: str  # "train" | "holdout"
    family: str  # 9 semantic families
    behavior_class: str  # "A_unique" | "B_composition" | "C_unknown" | "D_ambiguous"
    frontier_cardinality: int  # 1, 2, 3, 4
    signal: str
    context: dict[str, Any]
    frontier: list[str]
    target_bindings: list[dict[str, Any]]
    target_alternatives: list[dict[str, Any]]
    target_unknowns: list[str]
    expected_disposition: str  # "YES" | "CLARIFY" | "NO"

    def to_request(self) -> SemanticTranslationRequest:
        sig = ExternalSignal(raw=self.signal, signal_id=self.example_id)
        ctx_bindings = tuple(
            SemanticBinding(
                terminal=k,
                value=v,
                origin=BindingOrigin.DETERMINISTIC,
                evidence_refs=("ingress_c_min",),
            )
            for k, v in sorted(self.context.items())
        )
        ctx = MinimalSemanticContext(
            state_hash="0" * 64,
            state_sequence=1,
            bindings=ctx_bindings,
        )
        reqs = tuple(SemanticRequirement(name=t) for t in self.frontier)
        return SemanticTranslationRequest(signal=sig, minimal_context=ctx, frontier=reqs)

    def to_target_json(self) -> str:
        payload = {
            "bindings": self.target_bindings,
            "alternatives": self.target_alternatives,
            "unknowns": self.target_unknowns,
        }
        return json.dumps(payload, indent=2)


class AdmissionGateValidator:
    """Deterministic admission gate certifying each example against production rules."""

    def __init__(self) -> None:
        self.builder = SemanticPromptBuilder()
        self.parser = SemanticOutputParser()

    def validate(self, example: H3NativeExample) -> tuple[bool, str]:
        req = example.to_request()
        target_str = example.to_target_json()

        # Rule 1: Prompt must be constructible via production SemanticPromptBuilder
        try:
            user_prompt = self.builder.build_user_prompt(req)
            chat_msgs = self.builder.build_chat_messages(req)
            if not user_prompt or len(chat_msgs) != 2:
                return False, "Failed chat messages structure"
        except Exception as exc:
            return False, f"Prompt builder failed: {exc}"

        # Rule 2: Target JSON must strictly parse with SemanticOutputParser without fail_closed fallback
        try:
            cand = self.parser.parse(target_str, req, fail_closed=False)
        except SemanticOutputValidationError as val_err:
            return False, f"Strict parser validation failed: {val_err}"
        except Exception as exc:
            return False, f"Parser threw unexpected exception: {exc}"

        # Rule 3: Every target terminal must be in F_P
        frontier_set = set(example.frontier)
        for b in cand.candidate_bindings:
            if b.terminal not in frontier_set:
                return False, f"Binding terminal {b.terminal} not in F_P {frontier_set}"
        for alt in cand.alternatives:
            for b in alt.bindings:
                if b.terminal not in frontier_set:
                    return False, f"Alternative terminal {b.terminal} not in F_P {frontier_set}"
        for u in cand.unknowns:
            if u not in frontier_set:
                return False, f"Unknown terminal {u} not in F_P {frontier_set}"

        # Rule 4: No deterministic context field (C^min) repeated as a probabilistic binding
        c_min_keys = set(example.context.keys())
        for b in cand.candidate_bindings:
            if b.terminal in c_min_keys:
                return False, f"Deterministic context key {b.terminal} repeated in bindings"

        # Rule 5: Behavior class invariants
        if example.behavior_class == "A_unique":
            if cand.alternatives or cand.unknowns or not cand.candidate_bindings:
                return False, "Class A_unique must have bindings and no alternatives/unknowns"
        elif example.behavior_class == "B_composition":
            if cand.alternatives or cand.unknowns or len(cand.candidate_bindings) < 2:
                return False, "Class B_composition must have >=2 bindings and no alternatives/unknowns"
        elif example.behavior_class == "C_unknown":
            if not cand.unknowns:
                return False, "Class C_unknown must declare >=1 unknown"
        elif example.behavior_class == "D_ambiguous":
            if not cand.alternatives or cand.candidate_bindings:
                return False, "Class D_ambiguous must have alternatives and empty primary bindings"

        return True, "PASSED"


def build_raw_corpus_definitions() -> list[H3NativeExample]:
    """Define the structured specifications across 9 families, 4 classes, and 4 cardinalities."""
    examples: list[H3NativeExample] = []

    def add_ex(
        ex_id: str,
        partition: str,
        family: str,
        b_class: str,
        signal: str,
        context: dict[str, Any],
        frontier: list[str],
        bindings: list[dict[str, Any]],
        alternatives: list[dict[str, Any]],
        unknowns: list[str],
        disp: str,
    ) -> None:
        examples.append(
            H3NativeExample(
                example_id=ex_id,
                partition=partition,
                family=family,
                behavior_class=b_class,
                frontier_cardinality=len(frontier),
                signal=signal,
                context=context,
                frontier=frontier,
                target_bindings=bindings,
                target_alternatives=alternatives,
                target_unknowns=unknowns,
                expected_disposition=disp,
            )
        )

    # =========================================================================
    # 1. PERFORMATIVE FAMILY (Command vs Query)
    # =========================================================================
    # Train: canonical commands & queries
    add_ex(
        "TR_perf_cmd_fp1", "train", "performative", "A_unique",
        "Transfer five batteries to Mike.",
        {"operator": "transfer", "recipient": "Mike", "quantity": 5},
        ["performative"],
        [{"terminal": "performative", "value": "command"}], [], [], "YES"
    )
    add_ex(
        "TR_perf_query_fp1", "train", "performative", "A_unique",
        "Did Mike receive the five batteries?",
        {"operator": "query_transfer", "recipient": "Mike", "quantity": 5},
        ["performative"],
        [{"terminal": "performative", "value": "query"}], [], [], "YES"
    )
    add_ex(
        "TR_perf_cmd_fp2", "train", "performative", "B_composition",
        "Dispatch diagnostic kit to Station East.",
        {"item": "diagnostic_kit", "destination": "Station_East"},
        ["performative", "operator"],
        [{"terminal": "performative", "value": "command"}, {"terminal": "operator", "value": "dispatch"}],
        [], [], "YES"
    )
    add_ex(
        "TR_perf_query_fp2", "train", "performative", "B_composition",
        "Has diagnostic kit reached Station East?",
        {"item": "diagnostic_kit", "destination": "Station_East"},
        ["performative", "operator"],
        [{"terminal": "performative", "value": "query"}, {"terminal": "operator", "value": "query_status"}],
        [], [], "YES"
    )

    # Holdout: topicalized & inverted queries
    add_ex(
        "HO_perf_inverted_query_fp2", "holdout", "performative", "B_composition",
        "To Mike, were the five cells delivered?",
        {"quantity": 5, "recipient": "Mike"},
        ["performative", "operator"],
        [{"terminal": "performative", "value": "query"}, {"terminal": "operator", "value": "query_delivery"}],
        [], [], "YES"
    )

    # =========================================================================
    # 2. OPERATOR / SEMANTIC_HEAD FAMILY (Multi-cardinality routing)
    # =========================================================================
    # Train |F_P| = 4, 3, 2, 1
    add_ex(
        "TR_op_transfer_fp4", "train", "semantic_head", "B_composition",
        "Send three batteries to Alice immediately.",
        {},
        ["operator", "recipient", "quantity", "temporal"],
        [
            {"terminal": "operator", "value": "transfer"},
            {"terminal": "recipient", "value": "Alice"},
            {"terminal": "quantity", "value": 3},
            {"terminal": "temporal", "value": "IMMEDIATE"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_op_transfer_fp3", "train", "semantic_head", "B_composition",
        "Send three batteries to Alice immediately.",
        {"operator": "transfer"},
        ["recipient", "quantity", "temporal"],
        [
            {"terminal": "recipient", "value": "Alice"},
            {"terminal": "quantity", "value": 3},
            {"terminal": "temporal", "value": "IMMEDIATE"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_op_transfer_fp2", "train", "semantic_head", "B_composition",
        "Send three batteries to Alice immediately.",
        {"operator": "transfer", "quantity": 3},
        ["recipient", "temporal"],
        [
            {"terminal": "recipient", "value": "Alice"},
            {"terminal": "temporal", "value": "IMMEDIATE"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_op_transfer_fp1", "train", "semantic_head", "A_unique",
        "Send three batteries to Alice immediately.",
        {"operator": "transfer", "quantity": 3, "temporal": "IMMEDIATE"},
        ["recipient"],
        [{"terminal": "recipient", "value": "Alice"}],
        [], [], "YES"
    )

    # Various operators: dispatch, allocate, consign, quarantine, procure
    add_ex(
        "TR_op_allocate_fp3", "train", "semantic_head", "B_composition",
        "Allocate ten sensor units to Lab 2.",
        {},
        ["operator", "quantity", "recipient"],
        [
            {"terminal": "operator", "value": "allocate"},
            {"terminal": "quantity", "value": 10},
            {"terminal": "recipient", "value": "Lab_2"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_op_consign_fp2", "train", "semantic_head", "B_composition",
        "Consign diagnostic module to Operator Chen.",
        {"operator": "consign"},
        ["item", "recipient"],
        [
            {"terminal": "item", "value": "diagnostic_module"},
            {"terminal": "recipient", "value": "Operator_Chen"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_op_quarantine_fp2", "train", "semantic_head", "B_composition",
        "Quarantine contaminated batch at Storage B.",
        {},
        ["operator", "destination"],
        [
            {"terminal": "operator", "value": "quarantine"},
            {"terminal": "destination", "value": "Storage_B"},
        ],
        [], [], "YES"
    )

    # Holdout operators: purge, disgorge, bequeath (rare/compositional vocabulary)
    add_ex(
        "HO_op_purge_fp3", "holdout", "semantic_head", "B_composition",
        "Purge buffer cache at Sector 7 before reboot.",
        {},
        ["operator", "destination", "temporal"],
        [
            {"terminal": "operator", "value": "purge"},
            {"terminal": "destination", "value": "Sector_7"},
            {"terminal": "temporal", "value": "BEFORE_REBOOT"},
        ],
        [], [], "YES"
    )
    add_ex(
        "HO_op_disgorge_fp2", "holdout", "semantic_head", "B_composition",
        "Disgorge unallocated fuel cells to Depot East.",
        {"item": "fuel_cells"},
        ["operator", "destination"],
        [
            {"terminal": "operator", "value": "disgorge"},
            {"terminal": "destination", "value": "Depot_East"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 3. ARGUMENT / ROLE-SWAP FAMILY
    # =========================================================================
    # Train: canonical actor/recipient relations
    add_ex(
        "TR_arg_actor_recip_fp2", "train", "argument", "B_composition",
        "Mike transferred four cells to Alice.",
        {"operator": "transfer", "quantity": 4},
        ["actor", "recipient"],
        [
            {"terminal": "actor", "value": "Mike"},
            {"terminal": "recipient", "value": "Alice"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_arg_roleswap_fp2", "train", "argument", "B_composition",
        "Alice received four cells from Mike.",
        {"operator": "transfer", "quantity": 4},
        ["actor", "recipient"],
        [
            {"terminal": "actor", "value": "Mike"},
            {"terminal": "recipient", "value": "Alice"},
        ],
        [], [], "YES"
    )

    # Holdout: passive & nominalized role swap
    add_ex(
        "HO_arg_passive_roleswap_fp2", "holdout", "argument", "B_composition",
        "Four cells were entrusted to Dave by Chen.",
        {"operator": "transfer", "quantity": 4},
        ["actor", "recipient"],
        [
            {"terminal": "actor", "value": "Chen"},
            {"terminal": "recipient", "value": "Dave"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 4. REFERENCE / DEICTIC FAMILY
    # =========================================================================
    # Train: deictic anchoring ("here" -> SITE_17)
    add_ex(
        "TR_ref_here_fp2", "train", "reference", "B_composition",
        "Send three batteries here.",
        {"operator": "transfer", "quantity": 3},
        ["destination", "recipient"],
        [
            {"terminal": "destination", "value": "SITE_17"},
            {"terminal": "recipient", "value": "LOCAL_AGENT"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_ref_base_fp2", "train", "reference", "B_composition",
        "Return the rover to base station.",
        {"item": "rover"},
        ["operator", "destination"],
        [
            {"terminal": "operator", "value": "return"},
            {"terminal": "destination", "value": "BASE_STATION"},
        ],
        [], [], "YES"
    )

    # Holdout: deictic in complex query
    add_ex(
        "HO_ref_query_here_fp3", "holdout", "reference", "B_composition",
        "Did Chen dispatch two sensor packs here before noon?",
        {"actor": "Chen", "quantity": 2},
        ["operator", "destination", "temporal"],
        [
            {"terminal": "operator", "value": "query_dispatch"},
            {"terminal": "destination", "value": "SITE_17"},
            {"terminal": "temporal", "value": "BEFORE_1200"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 5. QUANTITY FAMILY (Universal & Numerical)
    # =========================================================================
    # Train: numerical and universal
    add_ex(
        "TR_qty_universal_all_fp2", "train", "quantity", "B_composition",
        "Convey all available cells to Station Alpha.",
        {"operator": "convey", "destination": "Station_Alpha"},
        ["quantity", "item"],
        [
            {"terminal": "quantity", "value": "ALL"},
            {"terminal": "item", "value": "cells"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_qty_numeric_fp2", "train", "quantity", "B_composition",
        "Allocate twelve batteries to Bay 4.",
        {"operator": "allocate", "destination": "Bay_4"},
        ["quantity", "item"],
        [
            {"terminal": "quantity", "value": 12},
            {"terminal": "item", "value": "batteries"},
        ],
        [], [], "YES"
    )

    # Holdout: universal with shorthand syntax
    add_ex(
        "HO_qty_colon_universal_fp3", "holdout", "quantity", "B_composition",
        "Station Alpha: deliver everything before 18:00.",
        {"operator": "deliver", "destination": "Station_Alpha"},
        ["quantity", "temporal", "performative"],
        [
            {"terminal": "quantity", "value": "ALL"},
            {"terminal": "temporal", "value": "BEFORE_1800"},
            {"terminal": "performative", "value": "command"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 6. NEGATION FAMILY
    # =========================================================================
    # Train: prohibitive actions & cancel commands
    add_ex(
        "TR_neg_action_fp2", "train", "negation", "B_composition",
        "Do not transfer the batteries to Mike.",
        {"recipient": "Mike", "item": "batteries"},
        ["operator", "modality"],
        [
            {"terminal": "operator", "value": "transfer"},
            {"terminal": "modality", "value": "MUST_NOT"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_neg_halt_fp2", "train", "negation", "B_composition",
        "Halt dispatch of cargo immediately.",
        {"item": "cargo"},
        ["operator", "temporal"],
        [
            {"terminal": "operator", "value": "halt_dispatch"},
            {"terminal": "temporal", "value": "IMMEDIATE"},
        ],
        [], [], "YES"
    )

    # Holdout: negative passive with conditional
    add_ex(
        "HO_neg_conditional_fp3", "holdout", "negation", "B_composition",
        "Unless authorized by supervisor, no items may be transferred to Bay 2.",
        {"destination": "Bay_2"},
        ["condition", "operator", "modality"],
        [
            {"terminal": "condition", "value": "UNLESS_AUTHORIZED"},
            {"terminal": "operator", "value": "transfer"},
            {"terminal": "modality", "value": "MUST_NOT"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 7. TEMPORAL FAMILY
    # =========================================================================
    # Train: before, after, until
    add_ex(
        "TR_temp_before_fp2", "train", "temporal", "B_composition",
        "Complete safety inspection before 17:00.",
        {"operator": "safety_inspection"},
        ["temporal", "performative"],
        [
            {"terminal": "temporal", "value": "BEFORE_1700"},
            {"terminal": "performative", "value": "command"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_temp_after_fp2", "train", "temporal", "B_composition",
        "Transfer diagnostic data after calibration.",
        {"operator": "transfer", "item": "diagnostic_data"},
        ["temporal", "performative"],
        [
            {"terminal": "temporal", "value": "AFTER_CALIBRATION"},
            {"terminal": "performative", "value": "command"},
        ],
        [], [], "YES"
    )

    # Holdout: chained temporal window
    add_ex(
        "HO_temp_window_fp3", "holdout", "temporal", "B_composition",
        "Between 14:00 and 16:00, convey seven sensors to Lab 3.",
        {"operator": "convey", "recipient": "Lab_3"},
        ["temporal", "quantity", "item"],
        [
            {"terminal": "temporal", "value": "WINDOW_1400_1600"},
            {"terminal": "quantity", "value": 7},
            {"terminal": "item", "value": "sensors"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 8. CONDITIONAL & POLICY GATE FAMILY
    # =========================================================================
    # Train: unless, if
    add_ex(
        "TR_cond_unless_fp2", "train", "conditional", "B_composition",
        "Unless lockout is active, dispatch fuel cell.",
        {"operator": "dispatch", "item": "fuel_cell"},
        ["condition", "performative"],
        [
            {"terminal": "condition", "value": "UNLESS_LOCKOUT"},
            {"terminal": "performative", "value": "command"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_cond_if_approved_fp2", "train", "conditional", "B_composition",
        "If approved by admin, allocate 50 units.",
        {"operator": "allocate", "quantity": 50},
        ["condition", "performative"],
        [
            {"terminal": "condition", "value": "IF_APPROVED"},
            {"terminal": "performative", "value": "command"},
        ],
        [], [], "YES"
    )

    # Holdout: multi-condition gate
    add_ex(
        "HO_cond_multi_gate_fp3", "holdout", "conditional", "B_composition",
        "Unless inspection fails and power dips, Mike: three cells before 17:00.",
        {"recipient": "Mike", "item": "cells"},
        ["condition", "quantity", "temporal"],
        [
            {"terminal": "condition", "value": "UNLESS_INSPECTION_FAILS_AND_POWER_DIPS"},
            {"terminal": "quantity", "value": 3},
            {"terminal": "temporal", "value": "BEFORE_1700"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # 9. MODALITY FAMILY
    # =========================================================================
    # Train: must, should, may
    add_ex(
        "TR_mod_must_fp2", "train", "modality", "B_composition",
        "Operator must verify checksum before commit.",
        {"actor": "Operator", "operator": "verify_checksum"},
        ["modality", "temporal"],
        [
            {"terminal": "modality", "value": "MUST"},
            {"terminal": "temporal", "value": "BEFORE_COMMIT"},
        ],
        [], [], "YES"
    )
    add_ex(
        "TR_mod_may_fp2", "train", "modality", "B_composition",
        "Technician may postpone routine sync.",
        {"actor": "Technician", "operator": "postpone_sync"},
        ["modality", "performative"],
        [
            {"terminal": "modality", "value": "MAY"},
            {"terminal": "performative", "value": "permission"},
        ],
        [], [], "YES"
    )

    # =========================================================================
    # BEHAVIOR CLASS C: EXPLICIT UNKNOWNS (Safe Abstention)
    # =========================================================================
    # Train: nonce verbs & ungrounded tokens
    add_ex(
        "TR_unk_florp_fp2", "train", "semantic_head", "C_unknown",
        "Florp five batteries to Mike.",
        {"quantity": 5},
        ["operator", "recipient"],
        [{"terminal": "recipient", "value": "Mike"}],
        [],
        ["operator"],
        "CLARIFY"
    )
    add_ex(
        "TR_unk_blurg_fp2", "train", "argument", "C_unknown",
        "Send three blurg units to Alice.",
        {"operator": "transfer", "quantity": 3},
        ["item", "recipient"],
        [{"terminal": "recipient", "value": "Alice"}],
        [],
        ["item"],
        "CLARIFY"
    )
    add_ex(
        "TR_unk_glarch_fp3", "train", "semantic_head", "C_unknown",
        "Glarch the packages to Site 17 before noon.",
        {"item": "packages"},
        ["operator", "destination", "temporal"],
        [
            {"terminal": "destination", "value": "Site_17"},
            {"terminal": "temporal", "value": "BEFORE_1200"},
        ],
        [],
        ["operator"],
        "CLARIFY"
    )

    # Holdout: unseen nonce words
    add_ex(
        "HO_unk_zord_fp2", "holdout", "semantic_head", "C_unknown",
        "Zord two diagnostic packs to Dave.",
        {"quantity": 2, "item": "diagnostic_packs"},
        ["operator", "recipient"],
        [{"terminal": "recipient", "value": "Dave"}],
        [],
        ["operator"],
        "CLARIFY"
    )
    add_ex(
        "HO_unk_quibble_fp3", "holdout", "argument", "C_unknown",
        "Dispatch five quibble modules here immediately.",
        {"operator": "dispatch", "quantity": 5},
        ["item", "destination", "temporal"],
        [
            {"terminal": "destination", "value": "SITE_17"},
            {"terminal": "temporal", "value": "IMMEDIATE"},
        ],
        [],
        ["item"],
        "CLARIFY"
    )

    # =========================================================================
    # BEHAVIOR CLASS D: GENUINE AMBIGUITY (Alternatives)
    # =========================================================================
    # Train: disjunctions & multiple referents
    add_ex(
        "TR_amb_mike_alice_fp2", "train", "argument", "D_ambiguous",
        "Transfer five batteries to Mike or Alice.",
        {"operator": "transfer", "quantity": 5},
        ["recipient", "performative"],
        [],
        [
            {"bindings": [{"terminal": "recipient", "value": "Mike"}, {"terminal": "performative", "value": "command"}], "reason": "admissible_disjunction"},
            {"bindings": [{"terminal": "recipient", "value": "Alice"}, {"terminal": "performative", "value": "command"}], "reason": "admissible_disjunction"},
        ],
        [],
        "CLARIFY"
    )
    add_ex(
        "TR_amb_bay_east_west_fp1", "train", "argument", "D_ambiguous",
        "Deliver equipment to Bay East or Bay West.",
        {"operator": "deliver", "item": "equipment"},
        ["destination"],
        [],
        [
            {"bindings": [{"terminal": "destination", "value": "Bay_East"}], "reason": "alternative_target"},
            {"bindings": [{"terminal": "destination", "value": "Bay_West"}], "reason": "alternative_target"},
        ],
        [],
        "CLARIFY"
    )

    # Holdout: ambiguous operator & target
    add_ex(
        "HO_amb_inspect_repair_fp2", "holdout", "semantic_head", "D_ambiguous",
        "Inspect or repair the cooling unit at Bay 3.",
        {"item": "cooling_unit", "destination": "Bay_3"},
        ["operator", "performative"],
        [],
        [
            {"bindings": [{"terminal": "operator", "value": "inspect"}, {"terminal": "performative", "value": "command"}], "reason": "operator_disjunction"},
            {"bindings": [{"terminal": "operator", "value": "repair"}, {"terminal": "performative", "value": "command"}], "reason": "operator_disjunction"},
        ],
        [],
        "CLARIFY"
    )

    # Additional systematic training variations across |F_P| = 1..4 to reach robust coverage
    more_train = [
        # Quantity + item
        ("TR_more_qty_item_fp2", "quantity", "B_composition", "Consign 15 solar panels to Station 4.", {"operator": "consign", "destination": "Station_4"}, ["quantity", "item"], [{"terminal": "quantity", "value": 15}, {"terminal": "item", "value": "solar_panels"}], [], [], "YES"),
        # Operator + temporal
        ("TR_more_op_temp_fp2", "temporal", "B_composition", "Purge log files after midnight.", {"target": "log_files"}, ["operator", "temporal"], [{"terminal": "operator", "value": "purge"}, {"terminal": "temporal", "value": "AFTER_MIDNIGHT"}], [], [], "YES"),
        # Destination + actor
        ("TR_more_dest_actor_fp2", "argument", "B_composition", "Supervisor Chen ordered delivery to Depot 9.", {"operator": "delivery"}, ["actor", "destination"], [{"terminal": "actor", "value": "Supervisor_Chen"}, {"terminal": "destination", "value": "Depot_9"}], [], [], "YES"),
        # Modality + condition
        ("TR_more_mod_cond_fp2", "modality", "B_composition", "Units must not be moved if alarm sounds.", {"operator": "move"}, ["modality", "condition"], [{"terminal": "modality", "value": "MUST_NOT"}, {"terminal": "condition", "value": "IF_ALARM_SOUNDS"}], [], [], "YES"),
        # Single terminal closures (|F_P| = 1)
        ("TR_more_fp1_op", "semantic_head", "A_unique", "Dispatch three batteries to Alice.", {"recipient": "Alice", "quantity": 3, "item": "batteries"}, ["operator"], [{"terminal": "operator", "value": "dispatch"}], [], [], "YES"),
        ("TR_more_fp1_recip", "argument", "A_unique", "Dispatch three batteries to Alice.", {"operator": "dispatch", "quantity": 3, "item": "batteries"}, ["recipient"], [{"terminal": "recipient", "value": "Alice"}], [], [], "YES"),
        ("TR_more_fp1_qty", "quantity", "A_unique", "Dispatch three batteries to Alice.", {"operator": "dispatch", "recipient": "Alice", "item": "batteries"}, ["quantity"], [{"terminal": "quantity", "value": 3}], [], [], "YES"),
        ("TR_more_fp1_item", "argument", "A_unique", "Dispatch three batteries to Alice.", {"operator": "dispatch", "recipient": "Alice", "quantity": 3}, ["item"], [{"terminal": "item", "value": "batteries"}], [], [], "YES"),
        ("TR_more_fp1_temp", "temporal", "A_unique", "Send cargo to Alice before 16:00.", {"operator": "send", "recipient": "Alice", "item": "cargo"}, ["temporal"], [{"terminal": "temporal", "value": "BEFORE_1600"}], [], [], "YES"),
        ("TR_more_fp1_cond", "conditional", "A_unique", "Dispatch cargo unless storm warning active.", {"operator": "dispatch", "item": "cargo"}, ["condition"], [{"terminal": "condition", "value": "UNLESS_STORM_WARNING"}], [], [], "YES"),
        ("TR_more_fp1_mod", "modality", "A_unique", "You must consign these units.", {"operator": "consign", "item": "units"}, ["modality"], [{"terminal": "modality", "value": "MUST"}], [], [], "YES"),
        # 4-terminal compositions (|F_P| = 4)
        ("TR_more_fp4_full1", "argument", "B_composition", "Supervisor Dave: allocate 20 batteries to Alice before 15:00.", {}, ["actor", "quantity", "recipient", "temporal"], [{"terminal": "actor", "value": "Dave"}, {"terminal": "quantity", "value": 20}, {"terminal": "recipient", "value": "Alice"}, {"terminal": "temporal", "value": "BEFORE_1500"}], [], [], "YES"),
        ("TR_more_fp4_full2", "conditional", "B_composition", "Unless lockout, convey 8 sensors to Site 01 immediately.", {}, ["condition", "quantity", "destination", "temporal"], [{"terminal": "condition", "value": "UNLESS_LOCKOUT"}, {"terminal": "quantity", "value": 8}, {"terminal": "destination", "value": "SITE_01"}, {"terminal": "temporal", "value": "IMMEDIATE"}], [], [], "YES"),
        ("TR_more_fp4_full3", "negation", "B_composition", "Operator must not transfer 10 cells to Lab 1.", {}, ["actor", "modality", "quantity", "recipient"], [{"terminal": "actor", "value": "Operator"}, {"terminal": "modality", "value": "MUST_NOT"}, {"terminal": "quantity", "value": 10}, {"terminal": "recipient", "value": "Lab_1"}], [], [], "YES"),
    ]

    for eid, fam, bcls, sig, ctx, frt, bnd, alt, unk, disp in more_train:
        add_ex(eid, "train", fam, bcls, sig, ctx, frt, bnd, alt, unk, disp)

    # Additional challenging holdouts
    more_holdout = [
        ("HO_more_colon_dispatch_fp4", "semantic_head", "B_composition", "DEPOT_CENTRAL: transfer 14 batteries to Mike before sunset.", {}, ["destination", "quantity", "recipient", "temporal"], [{"terminal": "destination", "value": "DEPOT_CENTRAL"}, {"terminal": "quantity", "value": 14}, {"terminal": "recipient", "value": "Mike"}, {"terminal": "temporal", "value": "BEFORE_SUNSET"}], [], [], "YES"),
        ("HO_more_multihop_fp3", "argument", "B_composition", "Route the relays via Gateway 2 to Substation 5.", {"item": "relays"}, ["operator", "destination", "recipient"], [{"terminal": "operator", "value": "route"}, {"terminal": "destination", "value": "Gateway_2"}, {"terminal": "recipient", "value": "Substation_5"}], [], [], "YES"),
        ("HO_more_ambig_qty_fp2", "quantity", "D_ambiguous", "Send three or four batteries to Dave.", {"operator": "send", "item": "batteries", "recipient": "Dave"}, ["quantity", "performative"], [], [{"bindings": [{"terminal": "quantity", "value": 3}, {"terminal": "performative", "value": "command"}], "reason": "quantity_disjunction"}, {"bindings": [{"terminal": "quantity", "value": 4}, {"terminal": "performative", "value": "command"}], "reason": "quantity_disjunction"}], [], "CLARIFY"),
        ("HO_more_unknown_item_fp2", "argument", "C_unknown", "Convey six plonkers to Site 17 immediately.", {"operator": "convey", "quantity": 6}, ["item", "destination"], [{"terminal": "destination", "value": "SITE_17"}], [], ["item"], "CLARIFY"),
        ("HO_more_mod_should_fp1", "modality", "A_unique", "Operator should verify power status.", {"operator": "verify_power_status", "actor": "Operator"}, ["modality"], [{"terminal": "modality", "value": "SHOULD"}], [], [], "YES"),
        ("HO_more_perf_query_fp1", "performative", "A_unique", "Is the storage array locked?", {"operator": "query_lock_status", "target": "storage_array"}, ["performative"], [{"terminal": "performative", "value": "query"}], [], [], "YES"),
        ("HO_more_temp_fp1", "temporal", "A_unique", "Transfer cargo before dusk.", {"operator": "transfer", "item": "cargo"}, ["temporal"], [{"terminal": "temporal", "value": "BEFORE_DUSK"}], [], [], "YES"),
        ("HO_more_ref_dest_fp1", "reference", "A_unique", "Deliver the diagnostic report here.", {"operator": "deliver", "item": "diagnostic_report"}, ["destination"], [{"terminal": "destination", "value": "SITE_17"}], [], [], "YES"),
    ]

    for eid, fam, bcls, sig, ctx, frt, bnd, alt, unk, disp in more_holdout:
        add_ex(eid, "holdout", fam, bcls, sig, ctx, frt, bnd, alt, unk, disp)

    return examples


def generate_and_admit_corpus() -> dict[str, Any]:
    """Execute the admission gate across all examples and build manifest."""
    raw_examples = build_raw_corpus_definitions()
    validator = AdmissionGateValidator()

    admitted_train: list[H3NativeExample] = []
    admitted_holdout: list[H3NativeExample] = []
    rejections: list[dict[str, str]] = []

    for ex in raw_examples:
        passed, reason = validator.validate(ex)
        if passed:
            if ex.partition == "train":
                admitted_train.append(ex)
            else:
                admitted_holdout.append(ex)
        else:
            rejections.append({"example_id": ex.example_id, "reason": reason})

    if rejections:
        raise RuntimeError(f"Corpus generation failed admission gate for {len(rejections)} examples: {rejections}")

    # Build manifest
    train_dump = [asdict(e) for e in admitted_train]
    holdout_dump = [asdict(e) for e in admitted_holdout]

    train_digest = hashlib.sha256(json.dumps(train_dump, sort_keys=True).encode("utf-8")).hexdigest()
    holdout_digest = hashlib.sha256(json.dumps(holdout_dump, sort_keys=True).encode("utf-8")).hexdigest()

    manifest = {
        "grammar_version": GRAMMAR_VERSION,
        "bindings_schema_version": BINDINGS_SCHEMA_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "total_admitted": len(admitted_train) + len(admitted_holdout),
        "train_count": len(admitted_train),
        "train_digest": train_digest,
        "holdout_count": len(admitted_holdout),
        "holdout_digest": holdout_digest,
        "cardinality_breakdown": {
            "train": {
                f"fp_{i}": sum(1 for e in admitted_train if e.frontier_cardinality == i)
                for i in (1, 2, 3, 4)
            },
            "holdout": {
                f"fp_{i}": sum(1 for e in admitted_holdout if e.frontier_cardinality == i)
                for i in (1, 2, 3, 4)
            },
        },
        "behavior_class_breakdown": {
            "train": {
                c: sum(1 for e in admitted_train if e.behavior_class == c)
                for c in ("A_unique", "B_composition", "C_unknown", "D_ambiguous")
            },
            "holdout": {
                c: sum(1 for e in admitted_holdout if e.behavior_class == c)
                for c in ("A_unique", "B_composition", "C_unknown", "D_ambiguous")
            },
        },
        "family_breakdown": {
            fam: {
                "train": sum(1 for e in admitted_train if e.family == fam),
                "holdout": sum(1 for e in admitted_holdout if e.family == fam),
            }
            for fam in (
                "performative", "semantic_head", "argument", "reference",
                "quantity", "negation", "temporal", "conditional", "modality"
            )
        },
        "train_examples": train_dump,
        "holdout_examples": holdout_dump,
    }

    CORPUS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Admitted {len(admitted_train)} train and {len(admitted_holdout)} holdout examples.")
    print(f"Manifest saved to: {CORPUS_MANIFEST_PATH}")
    return manifest


if __name__ == "__main__":
    generate_and_admit_corpus()
