from dataclasses import dataclass

from .adilang_ir import encode_plan


@dataclass(frozen=True)
class ActivityPlan:
    kind: str
    steps: list[str]
    ir: str


def plan_activity(message: str) -> ActivityPlan:
    text = message.lower()
    if any(word in text for word in ("edit", "ubah", "perbaiki", "tulis file", "write file")):
        kind = "workspace_change"
        steps = [
            "1:inspect_target:",
            "2:retrieve_constraints:1",
            "3:propose_change:1,2",
            "4:request_permission:3",
            "5:apply_minimal_change:4",
            "6:verify_result:5",
        ]
    elif any(word in text for word in ("gambar", "image", "foto", "screenshot", "layar")):
        kind = "vision_analysis"
        steps = ["1:validate_image:", "2:analyze_vision:1", "3:ground_findings:2", "4:answer:3"]
    elif any(word in text for word in ("kekurangan", "kelebihan", "analisa sistem", "analisis sistem", "kurang dari sistem", "evaluasi sistem")):
        kind = "system_evaluation"
        steps = [
            "1:diagnose_system_architecture:",
            "2:identify_real_bottlenecks:1",
            "3:formulate_actionable_plan:2",
            "4:verify_zero_hallucination:3",
            "5:propose_tool_execution:4",
        ]
    elif any(word in text for word in ("plan", "planning", "rencana")):
        kind = "action_planning"
        steps = [
            "1:analyze_objective:",
            "2:decompose_dag_tasks:1",
            "3:bind_executable_tools:2",
            "4:verify_constraints:3",
            "5:execute_or_report:4",
        ]
    elif any(word in text for word in ("buat", "generate", "rancang", "prompt", "draft")):
        kind = "creative_generation"
        steps = ["1:clarify_goal:", "2:retrieve_project_context:1", "3:draft:2", "4:check_constraints:3", "5:deliver:4"]
    else:
        kind = "grounded_answer"
        steps = ["1:normalize_intent:", "2:retrieve_evidence:1", "3:answer_from_evidence:2", "4:verify_citations:3"]
    return ActivityPlan(kind=kind, steps=steps, ir=encode_plan(kind, steps))

