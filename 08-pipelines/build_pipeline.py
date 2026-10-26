"""
A full, end-to-end SageMaker Pipeline for the gas-demand demo — a "real" ML DAG with a
quality gate, bias + explainability, and conditional model registration.

DAG:
  1. PreprocessTaxiData       (Processing)   ingest raw parquet -> clean -> split
  2. DataBiasCheck            (Clarify)      pre-training bias on the facet
  3. TrainTaxiModel           (Training)     custom train.py on the splits
  4. EvaluateModel            (Processing)   score test split -> evaluation.json
  5. CheckAUC                 (Condition)    only register if AUC >= threshold
        if passed:
  6.   CreateTaxiModel        (Model)        package the trained artifact
  7.   ModelBiasCheck         (Clarify)      post-training bias
  8.   ModelExplainabilityCheck(Clarify)     SHAP feature attributions
  9.   RegisterTaxiModel      (RegisterModel) versioned + metrics + drift baselines

We **upsert** the definition (create/update only — free, no compute). Run it live
with --start; each step is a short, cheap job. Clarify steps use skip_check=True +
register_new_baseline=True so the first run needs no prior baseline.

NOTE: the created model uses a fixed name (roi-smdemo-pipeline-model) so the Clarify
model checks can reference it; if you re-run, delete that model first (the cleanup
script does).

Usage:
    python build_pipeline.py --bucket roi-smdemo-029331796573-us-east-1 \
        --role-arn arn:aws:iam::029331796573:role/roi-smdemo-exec-role \
        --profile roitraining --region us-east-1 [--start]
"""

import argparse
import sys

import boto3
import sagemaker
from sagemaker import image_uris
from sagemaker.clarify import (
    BiasConfig, DataConfig, ModelConfig, ModelPredictedLabelConfig, SHAPConfig,
)
from sagemaker.inputs import TrainingInput
from sagemaker.model import Model
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.check_job_config import CheckJobConfig
from sagemaker.workflow.clarify_check_step import (
    ClarifyCheckStep, DataBiasCheckConfig, ModelBiasCheckConfig,
    ModelExplainabilityCheckConfig,
)
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import Join, JsonGet
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args


def _patch_repack_launcher_lf():
    """Force the SDK's generated _repack_script_launcher.sh to LF line endings.

    On Windows the SDK writes that bash launcher in text mode ("w"), so \\n becomes
    \\r\\n. The Linux repack container then chokes with '#015: not found' and a
    'model.tar.gz\\r' path, failing the CreateModel repack step. We re-implement the
    inject method verbatim but with newline="\\n". No-op effect on Linux (LF already).
    """
    import tarfile
    import tempfile
    from sagemaker.workflow import _utils as _u

    def _fixed(self):
        fname = _os.path.join(_os.path.dirname(_u.__file__), _u.REPACK_SCRIPT)
        launcher = _u.REPACK_SCRIPT_LAUNCHER
        if self._source_dir.lower().startswith("s3://"):
            with tempfile.TemporaryDirectory() as tmp:
                extracted = _os.path.join(tmp, "extracted")
                old_targz = _os.path.join(tmp, "old.tar.gz")
                _u.download_file_from_url(self._source_dir, old_targz, self.sagemaker_session)
                with tarfile.open(name=old_targz, mode="r:gz") as t:
                    _u.custom_extractall_tarfile(t, extracted)
                _u.shutil.copy2(fname, _os.path.join(extracted, _u.REPACK_SCRIPT))
                with open(_os.path.join(extracted, launcher), "w", newline="\n") as f:
                    f.write(_u.LAUNCH_REPACK_SCRIPT_CMD)
                new_targz = _os.path.join(tmp, "new.tar.gz")
                with tarfile.open(new_targz, mode="w:gz") as t:
                    t.add(extracted, arcname=_os.path.sep)
                _u._save_model(self._source_dir, new_targz, self.sagemaker_session, kms_key=None)
        else:
            _u.shutil.copy2(fname, _os.path.join(self._source_dir, _u.REPACK_SCRIPT))
            with open(_os.path.join(self._source_dir, launcher), "w", newline="\n") as f:
                f.write(_u.LAUNCH_REPACK_SCRIPT_CMD)

    _u._RepackModelStep._inject_repack_script_and_launcher = _fixed


_patch_repack_launcher_lf()

PIPELINE_NAME = config.resource("pipeline")
MODEL_PACKAGE_GROUP = config.resource("models")
MODEL_NAME = config.resource("pipeline-model")

# MUST stay in lockstep with FEATURES in 08-pipelines/preprocess.py. The schema
# is fixed and un-one-hot-encoded precisely so Clarify can declare headers.
LABEL = "high_demand"
FEATURES = [
    "temp_max_c", "temp_min_c", "temp_mean_f", "temp_range_c",
    "precip_mm", "precip_reported", "hdd65", "elevation_m",
    "obs_month", "is_weekend", "is_heating_season",
]
HEADERS = [LABEL] + FEATURES
# Bias facet: does the model behave differently in the heating season? For a gas
# utility that is the question that matters -- a demand model that is only
# accurate half the year fails exactly when you need it.
FACET = "is_heating_season"
# A representative feature row (no label) used as the SHAP baseline: a mild
# spring day at a low-elevation station.
SHAP_BASELINE = [[20.0, 10.0, 59.0, 10.0, 0.0, 1, 6.0, 100.0, 4, 0, 0]]


def main() -> int:
    p = argparse.ArgumentParser()
    add_common_args(p)
    p.add_argument("--start", action="store_true")
    args = p.parse_args()

    boto_sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    pipe_sess = PipelineSession(boto_session=boto_sess)
    b, role = args.bucket, args.role_arn
    image = image_uris.retrieve("sklearn", args.region, version="1.2-1")

    # ---- 1) Preprocess ----------------------------------------------------
    processor = SKLearnProcessor(
        framework_version="1.2-1", role=role, instance_type="ml.m5.2xlarge",
        instance_count=1, sagemaker_session=pipe_sess, base_job_name="roi-smdemo-preprocess",
    )
    proc_args = processor.run(
        code="08-pipelines/preprocess.py",
        inputs=[ProcessingInput(source=f"s3://{b}/processed/visual-etl/", destination="/opt/ml/processing/input")],
        outputs=[
            ProcessingOutput(output_name="train", source="/opt/ml/processing/output/train", destination=f"s3://{b}/pipeline/train"),
            ProcessingOutput(output_name="validation", source="/opt/ml/processing/output/validation", destination=f"s3://{b}/pipeline/validation"),
            ProcessingOutput(output_name="test", source="/opt/ml/processing/output/test", destination=f"s3://{b}/pipeline/test"),
        ],
    )
    step_process = ProcessingStep(name="PreprocessTaxiData", step_args=proc_args)
    out = step_process.properties.ProcessingOutputConfig.Outputs
    train_uri, val_uri, test_uri = (
        out["train"].S3Output.S3Uri, out["validation"].S3Output.S3Uri, out["test"].S3Output.S3Uri,
    )

    check_job_config = CheckJobConfig(
        role=role, instance_count=1, instance_type="ml.m5.large", sagemaker_session=pipe_sess,
    )

    # ---- 2) Data bias (pre-training) -------------------------------------
    step_data_bias = ClarifyCheckStep(
        name="DataBiasCheck",
        clarify_check_config=DataBiasCheckConfig(
            data_config=DataConfig(
                s3_data_input_path=train_uri, s3_output_path=f"s3://{b}/pipeline/clarify/databias",
                label=LABEL, headers=HEADERS, dataset_type="text/csv",
            ),
            data_bias_config=BiasConfig(label_values_or_threshold=[1], facet_name=FACET),
        ),
        check_job_config=check_job_config, skip_check=True, register_new_baseline=True,
    )

    # ---- 3) Train ---------------------------------------------------------
    estimator = SKLearn(
        entry_point="train.py", source_dir="04-training", role=role,
        instance_type="ml.m5.large", instance_count=1, framework_version="1.2-1",
        sagemaker_session=pipe_sess,
        hyperparameters={"learning-rate": 0.1, "n-estimators": 150, "max-depth": 3},
        metric_definitions=[{"Name": "validation:auc", "Regex": "validation_auc=([0-9\\.]+)"}],
    )
    step_train = TrainingStep(name="TrainTaxiModel", step_args=estimator.fit({
        "train": TrainingInput(train_uri, content_type="text/csv"),
        "validation": TrainingInput(val_uri, content_type="text/csv"),
    }))
    step_train.add_depends_on([step_data_bias])
    model_artifact = step_train.properties.ModelArtifacts.S3ModelArtifacts

    # ---- 4) Evaluate ------------------------------------------------------
    eval_processor = SKLearnProcessor(
        framework_version="1.2-1", role=role, instance_type="ml.m5.large",
        instance_count=1, sagemaker_session=pipe_sess, base_job_name="roi-smdemo-evaluate",
    )
    eval_report = PropertyFile(name="EvalReport", output_name="evaluation", path="evaluation.json")
    step_eval = ProcessingStep(
        name="EvaluateModel",
        step_args=eval_processor.run(
            code="08-pipelines/evaluate.py",
            inputs=[
                ProcessingInput(source=model_artifact, destination="/opt/ml/processing/model"),
                ProcessingInput(source=test_uri, destination="/opt/ml/processing/test"),
            ],
            outputs=[ProcessingOutput(output_name="evaluation", source="/opt/ml/processing/evaluation", destination=f"s3://{b}/pipeline/evaluation")],
        ),
        property_files=[eval_report],
    )

    # ---- 6) Create model (fixed name so Clarify can reference it) ---------
    model = Model(
        image_uri=image, model_data=model_artifact, role=role,
        name=MODEL_NAME, sagemaker_session=pipe_sess,
        entry_point="train.py", source_dir="04-training",
    )
    step_create_model = ModelStep(name="CreateTaxiModel", step_args=model.create(instance_type="ml.m5.large"))

    # ---- 7) Model bias (post-training) -----------------------------------
    # ModelStep ignores the fixed name= and generates its own model name at run
    # time, so reference the actual created name via the step property (a literal
    # MODEL_NAME here fails Clarify with "Could not find model ...").
    model_config = ModelConfig(
        model_name=step_create_model.properties.ModelName,
        instance_count=1, instance_type="ml.m5.large",
        accept_type="text/csv", content_type="text/csv",
    )
    step_model_bias = ClarifyCheckStep(
        name="ModelBiasCheck",
        clarify_check_config=ModelBiasCheckConfig(
            data_config=DataConfig(
                s3_data_input_path=test_uri, s3_output_path=f"s3://{b}/pipeline/clarify/modelbias",
                label=LABEL, headers=HEADERS, dataset_type="text/csv",
            ),
            data_bias_config=BiasConfig(label_values_or_threshold=[1], facet_name=FACET),
            model_config=model_config,
            model_predicted_label_config=ModelPredictedLabelConfig(probability_threshold=0.5),
        ),
        check_job_config=check_job_config, skip_check=True, register_new_baseline=True,
    )
    step_model_bias.add_depends_on([step_create_model])

    # ---- 8) Model explainability (SHAP) ----------------------------------
    step_explain = ClarifyCheckStep(
        name="ModelExplainabilityCheck",
        clarify_check_config=ModelExplainabilityCheckConfig(
            data_config=DataConfig(
                s3_data_input_path=test_uri, s3_output_path=f"s3://{b}/pipeline/clarify/explain",
                label=LABEL, headers=HEADERS, dataset_type="text/csv",
            ),
            model_config=model_config,
            explainability_config=SHAPConfig(baseline=SHAP_BASELINE, num_samples=50, agg_method="mean_abs"),
        ),
        check_job_config=check_job_config, skip_check=True, register_new_baseline=True,
    )
    step_explain.add_depends_on([step_create_model])

    # ---- 9) Register (with eval metrics) ---------------------------------
    model_metrics = ModelMetrics(
        model_statistics=MetricsSource(
            s3_uri=Join(on="/", values=[
                step_eval.properties.ProcessingOutputConfig.Outputs["evaluation"].S3Output.S3Uri,
                "evaluation.json",
            ]),
            content_type="application/json",
        )
    )
    step_register = RegisterModel(
        name="RegisterTaxiModel", estimator=estimator, model_data=model_artifact,
        content_types=["text/csv"], response_types=["text/csv"],
        inference_instances=["ml.m5.large"], transform_instances=["ml.m5.large"],
        model_package_group_name=MODEL_PACKAGE_GROUP, approval_status="Approved",
        model_metrics=model_metrics,
    )

    # ---- 5) Condition gate: register branch only if AUC >= 0.55 ----------
    step_condition = ConditionStep(
        name="CheckAUC",
        conditions=[ConditionGreaterThanOrEqualTo(
            left=JsonGet(step_name=step_eval.name, property_file=eval_report,
                         json_path="binary_classification_metrics.auc.value"),
            right=0.55,
        )],
        if_steps=[step_create_model, step_model_bias, step_explain, step_register],
        else_steps=[],
    )

    pipeline = Pipeline(
        name=PIPELINE_NAME,
        steps=[step_process, step_data_bias, step_train, step_eval, step_condition],
        sagemaker_session=pipe_sess,
    )
    pipeline.upsert(role_arn=role)
    print(f"upserted pipeline '{PIPELINE_NAME}' — 9 steps incl. eval gate, bias, SHAP (no run)")

    if args.start:
        print("started:", pipeline.start().arn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
