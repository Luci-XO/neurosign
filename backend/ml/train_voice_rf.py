"""
train_voice_rf.py
------------------
Trains a Random Forest on the UCI Oxford Parkinson's voice dataset
(parkinsons.data) and saves it to ml/models/voice_rf.joblib for the Flask
backend to load at inference time.

IMPORTANT - feature parity:
The UCI dataset has 22 features computed with Kay Elemetrics' MDVP
software (proprietary, not available to us). Our live inference uses
Praat/parselmouth instead (see analysis/voice_features.py), which computes
similar but not numerically identical quantities, and cannot reproduce
MDVP-only nonlinear measures (RPDE, DFA, spread1, spread2, D2, PPE).

So this script trains ONLY on the 10 features both MDVP and Praat can
compute in a directly comparable way:
    jitter(local), jitter(RAP), jitter(PPQ), jitter(DDP),
    shimmer(local), shimmer(dB), shimmer(APQ3), shimmer(APQ5),
    shimmer(DDA), HNR
This keeps training and inference features consistent, at the cost of
using less information than the full 22-feature dataset would allow.

IMPORTANT - evaluation methodology (v2):
The 195 recordings come from only 31 people (about 6 recordings each),
with far more PD subjects than healthy ones. A single random 75/25
subject split (v1 of this script) can easily starve one class out of the
test set by chance, producing wildly unstable metrics - which is exactly
what happened (0.12 precision on Healthy from a test set with only 1-2
healthy subjects in it).

This version fixes that two ways:
  1. StratifiedGroupKFold - keeps each person's recordings together in
     one fold (no leakage) AND tries to balance the Healthy/PD ratio
     across folds (so no fold is left with almost no healthy subjects).
  2. Out-of-fold evaluation on the WHOLE dataset via cross_val_predict -
     every recording gets predicted exactly once, only by a model that
     never saw that recording's subject during training. This uses all
     195 recordings for evaluation instead of just a 49-recording slice,
     which is far more stable with a dataset this small.

The final deployed model is then fit on ALL the data (standard practice:
cross-validation estimates how well the approach generalizes; the shipped
model itself should still learn from every available example).

Run from the backend/ folder:
    python ml/train_voice_rf.py
"""

import re
import sys
from pathlib import Path

# Allow "import config" etc. to find backend/ when this script is run
# directly (python ml/train_voice_rf.py) instead of as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
import joblib

import config

DATA_PATH = config.BACKEND_DIR / "parkinsons.data"

# Map from this script's column names to the UCI dataset's column names -
# these are the 10 features Praat can also compute at inference time.
FEATURE_COLUMNS = {
    "jitter_local": "MDVP:Jitter(%)",
    "jitter_rap": "MDVP:RAP",
    "jitter_ppq5": "MDVP:PPQ",
    "jitter_ddp": "Jitter:DDP",
    "shimmer_local": "MDVP:Shimmer",
    "shimmer_db": "MDVP:Shimmer(dB)",
    "shimmer_apq3": "Shimmer:APQ3",
    "shimmer_apq5": "Shimmer:APQ5",
    "shimmer_dda": "Shimmer:DDA",
    "hnr": "HNR",
}

# This MUST match MODEL_FEATURE_ORDER in backend/routes/voice.py
MODEL_FEATURE_ORDER = [
    "jitter_local", "jitter_rap", "jitter_ppq5", "jitter_ddp",
    "shimmer_local", "shimmer_db", "shimmer_apq3", "shimmer_apq5",
    "shimmer_dda", "hnr",
]

N_FOLDS = 5


def extract_subject_id(name: str) -> str:
    """The 'name' column looks like 'phon_R01_S01_1' - the S01 part
    identifies the subject/person. We group by that so the same person
    never appears in both train and test folds."""
    match = re.search(r"_S(\d+)_", name)
    if match:
        return match.group(1)
    return name  # fallback: treat as its own group


def build_model():
    """Single place that defines the model, so the CV loop and the final
    fit use identical settings."""
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=3,
        class_weight="balanced",  # dataset is imbalanced (more PD than healthy)
        random_state=42,
    )


def main():
    if not DATA_PATH.exists():
        print(f"ERROR: {DATA_PATH} not found.")
        print("Download it from https://archive.ics.uci.edu/dataset/174/parkinsons")
        print("and place 'parkinsons.data' inside the backend/ folder.")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} recordings.")

    df["subject_id"] = df["name"].apply(extract_subject_id)

    # One row per subject, to report the true Healthy/PD split by PERSON
    # (not by recording, which over-counts subjects with more recordings).
    subject_status = df.groupby("subject_id")["status"].first()
    n_healthy_subjects = int((subject_status == 0).sum())
    n_pd_subjects = int((subject_status == 1).sum())
    print(
        f"Recordings come from {len(subject_status)} distinct subjects "
        f"({n_healthy_subjects} healthy, {n_pd_subjects} PD)."
    )

    X = df[[FEATURE_COLUMNS[f] for f in MODEL_FEATURE_ORDER]].values
    y = df["status"].values  # 1 = Parkinson's, 0 = healthy
    groups = df["subject_id"].values

    # StratifiedGroupKFold: subjects never split across folds (no
    # leakage), AND folds are balanced by class as much as grouping
    # allows (so no fold is starved of healthy subjects like before).
    cv = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)

    model = build_model()

    # Out-of-fold predictions: every recording is predicted by a model
    # that never trained on that recording's subject. This gives one
    # evaluation set covering ALL 195 recordings instead of a single
    # small held-out slice.
    y_proba_oof = cross_val_predict(
        model, X, y, groups=groups, cv=cv, method="predict_proba",
    )[:, 1]
    y_pred_oof = (y_proba_oof >= 0.5).astype(int)

    print(f"\n{N_FOLDS}-fold stratified-grouped out-of-fold evaluation "
          f"(every recording predicted by a model that never saw its subject):")
    print(classification_report(y, y_pred_oof, target_names=["Healthy", "PD"]))
    print(f"Out-of-fold ROC-AUC: {roc_auc_score(y, y_proba_oof):.3f}")

    cm = confusion_matrix(y, y_pred_oof)
    print("\nConfusion matrix (rows=actual, cols=predicted) [Healthy, PD]:")
    print(cm)

    # Also report per-fold ROC-AUC so we can see how much it varies
    # fold-to-fold (a small dataset will still show some spread - that's
    # honest, not a bug).
    per_fold_aucs = []
    for fold_i, (train_idx, test_idx) in enumerate(cv.split(X, y, groups)):
        fold_model = build_model()
        fold_model.fit(X[train_idx], y[train_idx])
        proba = fold_model.predict_proba(X[test_idx])[:, 1]
        # Guard against a fold's test set having only one class present,
        # which makes ROC-AUC undefined.
        if len(set(y[test_idx])) < 2:
            print(f"  Fold {fold_i + 1}: skipped (test fold has only one class)")
            continue
        auc = roc_auc_score(y[test_idx], proba)
        per_fold_aucs.append(auc)
        print(f"  Fold {fold_i + 1}: {len(test_idx)} recordings, ROC-AUC = {auc:.3f}")

    if per_fold_aucs:
        print(
            f"\nMean per-fold ROC-AUC: {np.mean(per_fold_aucs):.3f} "
            f"(+/- {np.std(per_fold_aucs):.3f}, over {len(per_fold_aucs)} folds)"
        )

    # Final deployed model: fit on ALL available data. Cross-validation
    # above estimates how well this approach generalizes; the shipped
    # model should still learn from every example we have.
    final_model = build_model()
    final_model.fit(X, y)

    print("\nFeature importances (final model):")
    for name, importance in sorted(
        zip(MODEL_FEATURE_ORDER, final_model.feature_importances_),
        key=lambda pair: -pair[1],
    ):
        print(f"  {name:20s} {importance:.3f}")

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, config.VOICE_MODEL_PATH)
    print(f"\nSaved model to {config.VOICE_MODEL_PATH}")
    print(
        "\nNOTE: This model was trained on features computed with MDVP "
        "software. Live inference uses Praat-derived approximations of "
        "the same measures (see analysis/voice_features.py) - treat "
        "probabilities as indicative, not clinically validated. "
        "Reported metrics above are out-of-fold estimates from "
        "cross-validation, not a held-out test set - with only 31 "
        "subjects total, this is the most stable evaluation this "
        "dataset supports."
    )


if __name__ == "__main__":
    main()