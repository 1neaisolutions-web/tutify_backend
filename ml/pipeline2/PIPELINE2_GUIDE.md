# Pipeline2 Teacher Clustering – Beginner Guide

This guide is for interns or new contributors who want to understand, run, and safely extend the **Pipeline2 teacher clustering** module.

The goal of this pipeline is to group teachers into semantic clusters based on a generated text profile (`Teacher_profile`) and sentence embeddings.

---

## 1. High-level overview

- **Input**: CSV of teacher records (`Dummy_Teachers_Data_version2.csv`).
- **Feature**: A synthetic text field `Teacher_profile` built from multiple columns.
- **Model**:
  - Embeddings from `sentence-transformers/all-MiniLM-L6-v2`.
  - KMeans clustering on normalized embeddings.
  - Automatic selection of the best number of clusters \(K\) (between 2 and 15).
- **Outputs**:
  - Model artifacts in `model_registry/pipeline2/<version>/`.
  - Cluster predictions in `outputs/pipeline2/predictions.json`.
  - Run logs in `logs/pipeline2.log`.

Everything is designed to be:

- **Reproducible** (fixed random seeds, version-pinned dependencies).
- **CLI-driven** (run from terminal).
- **Backend-compatible** (no changes to existing API routes).

---

## 2. Repository structure (relevant parts)

Key folders for Pipeline2:

- `ml/`
  - `common/`
    - `logging.py`: shared logger utilities.
    - `validation.py`: dataset validation and hashing.
  - `pipeline2/`
    - `__init__.py`: marks this as a package.
    - `dataset.py`: loads CSV and builds `Teacher_profile`.
    - `feature_spec.py`: configuration for features and model (e.g., text column, model name, K range).
    - `train.py`: training logic (embeddings, KMeans, metrics, artifacts).
    - `model.py`: loading a trained model and running predictions.
    - `artifacts.py`: reading/writing artifacts under `model_registry/pipeline2/`.
    - `cli.py`: command-line interface (`python -m ml.pipeline2.cli ...`).
    - `PIPELINE2_GUIDE.md`: **this guide**.

- `tools/ml/`
  - `run_pipeline2_local.py`: friendly wrapper for local training/prediction commands.

- `model_registry/pipeline2/`
  - Versioned model directories created after training, e.g.:
    - `pipeline2-2026-03-05-001/`

- `outputs/pipeline2/`
  - `predictions.json`: predictions produced by `predict` command.

- `logs/`
  - `pipeline2.log`: JSON log lines for each train/predict run.

---

## 3. Environment setup

### 3.1. Python version

Use **Python 3.11** (the project was validated with 3.11.6 on Windows).

You can check your version:

```bash
python --version
```

If this reports something very different (e.g. 3.8), create/activate a 3.11 virtual environment before proceeding.

### 3.2. Install ML requirements

Make sure you are in the backend root directory:

```bash
cd c:\Users\Wajeeha Ahmad\Desktop\1ne_ai\1ne_backend
```

Install ML-specific dependencies:

```bash
pip install -r requirements-ml.txt
```

Pinned versions:

- `sentence-transformers==2.7.0`
- `scikit-learn==1.4.2`
- `pandas==2.2.2`
- `numpy==2.4.2`
- `kneed==0.8.5`
- `joblib==1.3.2`
- `tqdm==4.66.4`

> Note: These are **separate** from the main backend requirements to avoid conflicts.

### 3.3. Quick import test

To confirm the ML env is healthy:

```bash
python -c "import numpy, pandas, sklearn, tqdm, joblib, kneed; print('ML imports OK')"
```

If this prints `ML imports OK`, you’re good to go.

---

## 4. Data: CSV and Teacher_profile generation

Default dataset (checked into the repo):

- `Dummy_Teachers_Data_version2.csv`

Required columns for generating `Teacher_profile`:

- `Subject`
- `Grade_Level`
- `Years_Exp`
- `Skills`
- `School_SES_Rating`
- `Student_Teacher_Ratio`
- `Regional_Priority_Skills`
- `Region`

### 4.1. `Teacher_profile` logic

This column **does not exist** in the original CSV. It is created in-memory in `dataset.py` using:

```python
def teacher_to_text(row):
    economic_label = (
        "low income school" if row["School_SES_Rating"] < 0.5
        else "moderate income school"
    )

    class_label = (
        "small class size"
        if row["Student_Teacher_Ratio"] < 25
        else "large class size"
    )

    return (
        f"Teaches {row['Subject']} to {row['Grade_Level']} grade. "
        f"Has {row['Years_Exp']} years of experience. "
        f"Expert in {row['Skills']}. "
        f"Works in a {economic_label} with {class_label}. "
        f"Regional Priority skills are :{row['Regional_Priority_Skills']}. "
        f"Region: {row['Region']}."
    )
```

Key points:

- If `Teacher_profile` already exists in the CSV, it is **used as-is**.
- If it does **not** exist, it is generated automatically.
- By default, the original CSV is **never modified on disk**.

To optionally persist a CSV including `Teacher_profile`, you can use the `--persist-profile` flag during prediction (see below).

---

## 5. Training the clustering model

There are two ways to run training:

### 5.1. Recommended: local wrapper script

From the backend root:

```bash
python tools/ml/run_pipeline2_local.py train
```

This:

- Uses the default input: `Dummy_Teachers_Data_version2.csv`.
- Creates a version like `pipeline2-YYYY-MM-DD-001`.

You can override the version and input path:

```bash
python tools/ml/run_pipeline2_local.py train \
  --input path/to/your_teachers.csv \
  --version pipeline2-2026-03-05-001
```

### 5.2. Direct CLI invocation

Equivalent call via the pipeline module:

```bash
python -m ml.pipeline2.cli train \
  --input Dummy_Teachers_Data_version2.csv \
  --version pipeline2-2026-03-05-001
```

### 5.3. What happens during training (step-by-step)

1. **Load dataset** with pandas.
2. **Validate columns**: if any required column is missing, a clear `ValueError` is raised.
3. **Generate `Teacher_profile`** if missing, using the function above.
4. **Embed profiles**:
   - Loads `sentence-transformers/all-MiniLM-L6-v2`.
   - Encodes each `Teacher_profile` into a dense vector.
5. **Normalize embeddings**:
   - Applies `sklearn.preprocessing.normalize` (L2 norm) to the embedding matrix.
6. **Search for best K** (number of clusters):
   - K ranges from 2 to 15.
   - For each K:
     - Train `KMeans(n_clusters=k, random_state=42, n_init="auto", init="k-means++")`.
     - Record:
       - `inertia` (within-cluster sum of squares).
       - `silhouette_score` (if valid).
   - Use `KneeLocator` with:
     - `curve="convex"`, `direction="decreasing"` on the inertia curve.
   - **Selection rule**:
     1. If an elbow is detected → use that K.
     2. Otherwise, use K with the highest silhouette score.
     3. Tie-breaker: choose the **smallest** such K.
7. **Train final KMeans** with the selected K.
8. **Compute metrics**:
   - Final silhouette score.
   - Final inertia.
   - Cluster size counts.
   - Full inertia and silhouette curves over K=2..15.
9. **Save artifacts** to:
   - `model_registry/pipeline2/<version>/`
   - Files:
     - `model.pkl`
     - `feature_spec.json`
     - `metrics.json`
     - `manifest.json`
10. **Log run** to:
    - `logs/pipeline2.log` with `run_id`, `model_version`, `dataset_hash`, `runtime`, `status`, etc.

---

## 6. Running prediction

### 6.1. Recommended: local wrapper

From the backend root:

```bash
python tools/ml/run_pipeline2_local.py predict
```

Defaults:

- `--input`: `Dummy_Teachers_Data_version2.csv`
- `--version`: `latest` (picks the most recent model version in `model_registry/pipeline2/`).
- `--out`: `outputs/pipeline2/predictions.json`

You can override these:

```bash
python tools/ml/run_pipeline2_local.py predict \
  --input path/to/your_teachers.csv \
  --version pipeline2-2026-03-05-001 \
  --out outputs/pipeline2/my_predictions.json \
  --persist-profile outputs/pipeline2/teachers_with_profile.csv
```

### 6.2. Direct CLI

```bash
python -m ml.pipeline2.cli predict \
  --version latest \
  --input Dummy_Teachers_Data_version2.csv \
  --out outputs/pipeline2/predictions.json
```

### 6.3. Prediction output format

The JSON file looks like:

```json
{
  "version": "pipeline2-2026-03-05-001",
  "num_rows": 300,
  "predictions": [
    {
      "row_index": 0,
      "cluster_label": 2,
      "Teacher_ID": "T1000"
    }
  ]
}
```

Notes:

- `Teacher_ID` is included if one of `Teacher_ID`, `id`, or `teacher_id` is present in the dataset.
- `row_index` corresponds to the row index in the input CSV.

---

## 7. Artifacts and logs

### 7.1. Model artifacts

Location:

- `model_registry/pipeline2/<version>/`

Files:

- `model.pkl`: serialized KMeans + metadata.
- `feature_spec.json`: configuration for the pipeline (text column, embedding model, K range, etc.).
- `metrics.json`: training metrics, including:
  - `final_silhouette_score`
  - `final_inertia`
  - `cluster_counts`
  - `k_values`
  - `inertia` (per K)
  - `silhouette` (per K)
  - `selected_k`
  - `k_selection_method` (`"knee"` or `"silhouette"`).
- `manifest.json`: environment metadata:
  - Timestamp, Python version, platform.
  - Library versions.
  - `dataset_hash`.
  - `git_commit_hash` (if available).

### 7.2. Logs

Location:

- `logs/pipeline2.log`

Each line is a JSON record with fields such as:

- `run_id`
- `model_version`
- `dataset_hash`
- `runtime`
- `status` (`STARTED`, `SUCCESS`, or `FAILURE`)
- `error`
- `message`

These logs are meant for debugging and tracking experiments.

---

## 8. Service integration (high-level)

The pipeline is wired into a service stub for future backend integration:

- `app/domains/learning_hub/services/pipeline2_service.py`
  - `Pipeline2Service(model_version="latest")`
  - `predict_from_csv(csv_path, persist_profile_path=None)`:
    - Loads data.
    - Ensures `Teacher_profile`.
    - Runs predictions.
    - Returns a list of `{row_index, cluster_label, Teacher_ID?}`.

Currently this service reads from **CSV files** only. In the future it can be extended to:

- Pull teacher records from the database.
- Persist cluster assignments back to the DB.

---

## 9. Common issues & troubleshooting

### 9.1. `ModuleNotFoundError: No module named 'ml'`

- Make sure you are running commands from the project root:

  ```bash
  cd c:\Users\Wajeeha Ahmad\Desktop\1ne_ai\1ne_backend
  ```

- Prefer:

  ```bash
  python tools/ml/run_pipeline2_local.py train
  ```

  which adjusts `sys.path` to include the project root.

### 9.2. Import or version errors (pandas / numpy / sklearn)

- Reinstall ML requirements:

  ```bash
  pip install --force-reinstall -r requirements-ml.txt
  ```

- Then re-test:

  ```bash
  python -c "import numpy, pandas, sklearn, tqdm, joblib, kneed; print('ML imports OK')"
  ```

### 9.3. HuggingFace download issues or slowness

- The first run may be slow due to model download.
- You can re-run training later; the model is cached under your user’s HuggingFace cache directory.

---

## 10. Safe ways for an intern to extend the pipeline

If you are a beginner intern, stick to these safe kinds of changes:

- Add new **textual features** to the `Teacher_profile` string (only after confirming required columns exist).
- Add **new metrics** to `metrics.json` (e.g., per-cluster averages).
- Add simple **post-processing** on predictions (e.g., mapping cluster IDs to human-readable labels) in a separate module.

Avoid:

- Changing the main backend routes or DB models without mentor review.
- Modifying the K selection logic unless you fully understand KMeans and evaluation metrics.

If in doubt, ask a maintainer before changing anything outside `ml/pipeline2/` and `tools/ml/`.

---

## 11. Quick recap: two commands you must remember

From the backend root:

```bash
# Train
python tools/ml/run_pipeline2_local.py train

# Predict
python tools/ml/run_pipeline2_local.py predict
```

After running these, check:

- `model_registry/pipeline2/<version>/` for artifacts.
- `outputs/pipeline2/predictions.json` for cluster labels.
- `logs/pipeline2.log` for structured run logs.

That’s all you need to run and understand the Pipeline2 clustering workflow end-to-end. If anything is unclear, read this guide again and then inspect the code in `ml/pipeline2/` for more detail.

