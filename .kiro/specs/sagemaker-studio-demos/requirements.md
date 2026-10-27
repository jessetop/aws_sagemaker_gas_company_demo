# Requirements Document

## Introduction

This document defines the requirements for a progressive, educational demo series for an AWS SageMaker Studio class. The demo series guides learners through the end-to-end machine learning workflow on SageMaker, starting with dataset acquisition, progressing through custom training scripts and containers, experiment tracking, hyperparameter tuning, and finishing with model deployment and inference. Each demo builds on prior concepts to reinforce learning.

## Glossary

- **Demo_Series**: The complete set of progressive SageMaker Studio demonstrations delivered as part of the class
- **Demo_Module**: A single self-contained demonstration within the Demo_Series, focused on one concept
- **Dataset_Loader**: The component responsible for downloading and preparing the public dataset for use in training
- **Training_Script**: A Python script that defines model architecture, training loop, and metric logging for use with SageMaker training jobs
- **Custom_Container**: A Docker container image built from an AWS pre-built deep learning container (e.g., TensorFlow, PyTorch) with additional dependencies for training
- **Experiment_Tracker**: The SageMaker Experiments component used to organize, log, and compare training runs and metrics
- **Training_Job**: A SageMaker managed training job that executes a Training_Script on cloud compute
- **Tuning_Job**: A SageMaker hyperparameter tuning job that launches multiple Training_Jobs to find optimal hyperparameters
- **Model_Endpoint**: A SageMaker real-time inference endpoint serving a trained model
- **Learner**: A student or participant in the SageMaker Studio class
- **Instructor_Guide**: Commentary and explanations embedded in each Demo_Module to support teaching

## Requirements

### Requirement 1: Public Dataset Acquisition

**User Story:** As a Learner, I want to use a large, well-known public dataset, so that I can practice real-world data loading and preprocessing in SageMaker Studio.

#### Acceptance Criteria

1. THE Dataset_Loader SHALL download a publicly available tabular or image dataset of at least 100,000 samples suitable for classification or regression tasks
2. WHEN the dataset is downloaded, THE Dataset_Loader SHALL split it into training, validation, and test sets using Learner-provided ratios that each range from 0.1 to 0.8 and sum to 1.0, defaulting to 0.7 training, 0.15 validation, and 0.15 test when no ratios are provided
3. IF the Learner provides split ratios that do not each fall within 0.1 to 0.8 or do not sum to 1.0, THEN THE Dataset_Loader SHALL reject the request with an error message indicating the valid ratio constraints
4. WHEN the dataset is prepared, THE Dataset_Loader SHALL upload the splits to an S3 bucket path provided by the Learner
5. IF the dataset download fails due to network or source unavailability, THEN THE Dataset_Loader SHALL retry up to 3 times with a 5-second delay between attempts before returning an error message that includes the failure reason and the number of attempts made
6. IF the S3 upload fails for any split, THEN THE Dataset_Loader SHALL return an error message indicating which split failed to upload and the failure reason, without deleting any previously uploaded splits
7. THE Dataset_Loader SHALL include inline comments explaining each step of the data acquisition and preparation process

### Requirement 2: Custom Training Script Development

**User Story:** As a Learner, I want to create a custom training script compatible with SageMaker, so that I can understand how SageMaker executes training code.

#### Acceptance Criteria

1. THE Training_Script SHALL accept hyperparameters (learning rate, batch size, epochs) as command-line arguments parsed from SageMaker environment variables
2. THE Training_Script SHALL read training and validation data from the SageMaker input channel paths (SM_CHANNEL_TRAIN, SM_CHANNEL_VALIDATION)
3. WHEN a training epoch completes, THE Training_Script SHALL log training loss and validation accuracy metrics to stdout using the prefix format recognized by SageMaker (e.g., lines containing metric name, equals sign, and numeric value)
4. WHEN training completes, THE Training_Script SHALL save the trained model artifact to the SM_MODEL_DIR path in a format loadable by the chosen framework's standard model-loading function
5. THE Training_Script SHALL include inline comments explaining the SageMaker contract (environment variables, input channels, model output)
6. IF an invalid hyperparameter value is provided (learning rate not between 0.0001 and 1.0, batch size not between 1 and 512, or epochs not between 1 and 100), THEN THE Training_Script SHALL raise a ValueError with a message describing the acceptable range for the invalid parameter
7. IF a required input channel path (SM_CHANNEL_TRAIN or SM_CHANNEL_VALIDATION) does not exist or contains no data files, THEN THE Training_Script SHALL raise a FileNotFoundError with a message indicating which channel path is missing or empty

### Requirement 3: Custom Container Configuration

**User Story:** As a Learner, I want to build a custom training container from an AWS pre-built deep learning image, so that I can understand container-based training on SageMaker.

#### Acceptance Criteria

1. THE Custom_Container SHALL use an AWS pre-built TensorFlow or PyTorch deep learning container as its base image
2. THE Custom_Container SHALL include a Dockerfile with inline comments explaining each layer and its purpose
3. WHEN built, THE Custom_Container SHALL install all additional Python dependencies specified in a requirements.txt file
4. THE Custom_Container SHALL configure the SageMaker-required directory structure (/opt/ml subdirectories for input, output, and model) and set the entrypoint to invoke the Training_Script via a ENTRYPOINT or SAGEMAKER_PROGRAM environment variable
5. THE Demo_Module SHALL include step-by-step instructions for creating an ECR repository, authenticating Docker to ECR, building the Custom_Container image, and pushing it to the repository
6. IF the container build fails due to a missing dependency, THEN THE Custom_Container build process SHALL output an error message indicating which package could not be installed
7. THE Custom_Container SHALL copy the Training_Script into the container image so that the container is self-contained for SageMaker training job execution
8. THE Demo_Module SHALL include instructions for running the Custom_Container locally to verify the entrypoint and directory structure before pushing to ECR

### Requirement 4: SageMaker Experiments Tracking

**User Story:** As a Learner, I want to use SageMaker Experiments to track and compare training runs, so that I can understand how to organize ML experimentation.

#### Acceptance Criteria

1. WHEN a training run is initiated, THE Experiment_Tracker SHALL create or reuse an Experiment and create a new Run within it
2. WHEN metrics are logged during training, THE Experiment_Tracker SHALL record loss, accuracy, and custom metrics with non-negative integer step numbers
3. WHEN at least 2 runs exist within an Experiment, THE Experiment_Tracker SHALL provide code to compare metrics across runs in a tabular or visual format
4. WHEN a Run is created, THE Experiment_Tracker SHALL log hyperparameters, input dataset locations, and artifact output paths as run parameters
5. THE Demo_Module SHALL include code demonstrating how to query and retrieve past experiment results using the SageMaker SDK, displaying run names, parameters, and final metric values
6. IF an Experiment with the specified name already exists, THEN THE Experiment_Tracker SHALL reuse the existing Experiment without creating a duplicate
7. IF a metric logging call fails due to an invalid metric name or value, THEN THE Experiment_Tracker SHALL raise an error indicating the invalid metric details

### Requirement 5: SageMaker SDK Training Job Execution

**User Story:** As a Learner, I want to launch training jobs using the SageMaker Python SDK, so that I can understand managed training infrastructure.

#### Acceptance Criteria

1. THE Demo_Module SHALL demonstrate creating an Estimator with the SageMaker Python SDK specifying an IAM role, entry point Training_Script path, instance type, instance count of 1, and container image URI
2. WHEN the Estimator.fit() method is called with S3 input channel paths for training and validation data, THE Training_Job SHALL execute the Training_Script on the specified compute instance
3. THE Demo_Module SHALL demonstrate passing at least 3 hyperparameters (learning rate, batch size, epochs) to the Estimator and retrieving them inside the Training_Script via command-line arguments
4. WHEN the Estimator.fit() method is called, THE Demo_Module SHALL demonstrate monitoring job progress by enabling log streaming to display training output in the notebook
5. WHEN the Training_Job completes successfully, THE Demo_Module SHALL demonstrate how to retrieve the S3 model artifact path from the training job output
6. IF the Training_Job fails, THEN THE Demo_Module SHALL include error handling code that retrieves the failure reason from the job description and displays an error message indicating the cause of failure
7. THE Demo_Module SHALL include instructor commentary explaining the lifecycle of a SageMaker training job (provisioning, data download, training execution, model artifact upload to S3, instance teardown)

### Requirement 6: Hyperparameter Tuning

**User Story:** As a Learner, I want to run a hyperparameter tuning job, so that I can understand automated model optimization on SageMaker.

#### Acceptance Criteria

1. THE Tuning_Job SHALL define a search space with at least two continuous or categorical hyperparameters
2. THE Tuning_Job SHALL specify an objective metric name and optimization direction (minimize or maximize)
3. WHEN the Tuning_Job completes, THE Demo_Module SHALL retrieve and display the best hyperparameter combination and its objective metric value
4. THE Tuning_Job SHALL configure a maximum number of training jobs and maximum parallel jobs to control cost
5. THE Demo_Module SHALL include code to visualize tuning results showing how hyperparameter values relate to the objective metric
6. THE Demo_Module SHALL include instructor commentary explaining Bayesian optimization strategy and early stopping

### Requirement 7: Model Deployment and Inference

**User Story:** As a Learner, I want to deploy a trained model to a real-time endpoint, so that I can understand SageMaker model serving.

#### Acceptance Criteria

1. WHEN a trained model artifact is available in S3 from a completed Training_Job, THE Demo_Module SHALL demonstrate creating a SageMaker Model object referencing the artifact S3 path and the container image URI
2. WHEN the SageMaker Model object is created, THE Demo_Module SHALL demonstrate deploying the Model to a real-time Model_Endpoint with a specified instance type and an initial instance count of 1, waiting no longer than 15 minutes for deployment to complete
3. WHEN the Model_Endpoint status is InService, THE Demo_Module SHALL demonstrate sending at least 3 inference requests with sample data matching the model's expected input format and displaying the returned predictions
4. THE Demo_Module SHALL include code to delete the Model_Endpoint after the demo and confirm the deletion request was accepted to avoid ongoing charges
5. IF the Model_Endpoint does not reach InService status within 15 minutes, THEN THE Demo_Module SHALL include error handling code that retrieves and displays the endpoint failure reason from the endpoint description
6. THE Demo_Module SHALL include instructor commentary explaining endpoint auto-scaling options and cost considerations
7. IF an inference request to the Model_Endpoint returns an error, THEN THE Demo_Module SHALL include error handling code that displays the error response and verifies the Model_Endpoint is still InService

### Requirement 8: Progressive Demo Structure

**User Story:** As an Instructor, I want the demos to follow a progressive structure, so that each module builds upon concepts from prior modules.

#### Acceptance Criteria

1. THE Demo_Series SHALL organize modules in sequential order: Dataset Preparation, Training Script, Custom Container, Experiments Tracking, SDK Training Jobs, Hyperparameter Tuning, Model Deployment
2. WHEN a Demo_Module references a concept introduced in a prior module, THE Demo_Module SHALL include a cross-reference stating the source module title and section name where the concept was introduced
3. THE Demo_Series SHALL include a README file listing all modules, each with a 1-3 sentence description, required prerequisites, and estimated completion time in minutes
4. EACH Demo_Module SHALL include a "Learning Objectives" section as the first section after the module title, listing at least 2 measurable concepts the Learner will understand after completing the module
5. EACH Demo_Module SHALL include a "Prerequisites" section listing prior modules that must be completed and the specific AWS IAM permissions required to execute the module
6. THE Demo_Series SHALL include cleanup instructions containing executable commands or a script that tears down all provisioned resources (endpoints, ECR images, S3 data) after the class concludes
7. EACH Demo_Module SHALL include a "Starting State" section that describes the expected AWS environment state (resources, artifacts, and outputs from prior modules) required before the module can be executed
