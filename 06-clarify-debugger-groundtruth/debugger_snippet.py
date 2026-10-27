"""
Module 6B — SageMaker Debugger, the old way (snippet to fold into Module 4).

Shows how Debugger attaches to the SAME SKLearn estimator from Module 4: capture
tensors during training and evaluate built-in rules. In Unified Studio this insight
shows up in the project training view (SageMaker Profiler), with far less wiring.

This is a snippet, not a standalone run — drop these kwargs into launch_training.py's
estimator to demo Debugger live (adds negligible cost to the training job).
"""

from sagemaker.debugger import Rule, rule_configs, DebuggerHookConfig, CollectionConfig

# Built-in rules evaluate common training pathologies for free, in parallel.
debugger_rules = [
    Rule.sagemaker(rule_configs.loss_not_decreasing()),
    Rule.sagemaker(rule_configs.overfit()),
]

# Hook config controls which tensors are saved and how often.
debugger_hook_config = DebuggerHookConfig(
    collection_configs=[
        CollectionConfig(name="metrics", parameters={"save_interval": "10"}),
    ]
)

# Usage inside launch_training.py:
#
#   estimator = SKLearn(
#       ...,
#       rules=debugger_rules,
#       debugger_hook_config=debugger_hook_config,
#   )
#   estimator.fit(...)
#   # then inspect rule status:
#   for s in estimator.latest_training_job.rule_job_summary():
#       print(s["RuleConfigurationName"], s["RuleEvaluationStatus"])
#
# NEW way: open the project's training job → "Debugger / Profiler insights" tab;
# the same rule outcomes and resource utilization appear without this boilerplate.
