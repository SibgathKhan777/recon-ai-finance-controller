"""End-to-end test of the training pipeline, kept fast with a tiny seed
range -- this exercises the real code path (dataset build, fit, predict,
skops save/load, the deterministic-matcher comparison) rather than a full
70-seed training run, which would be too slow for the regular test suite."""
import skops.io as sio

from ml import train as train_module
from ml.features import FEATURE_NAMES
from recon.generate_data import generate


def teardown_module(module):
    generate(seed=42)


def test_training_pipeline_runs_end_to_end_and_produces_a_loadable_model(tmp_path, monkeypatch):
    monkeypatch.setattr(train_module, "TRAIN_SEEDS", [1, 2, 3])
    monkeypatch.setattr(train_module, "TEST_SEEDS", [4, 5])
    monkeypatch.setattr(train_module, "MODEL_PATH", tmp_path / "model.skops")
    monkeypatch.setattr(train_module, "REPORT_PATH", tmp_path / "report.json")

    report = train_module.train()

    assert report["train_examples"] > 0
    assert report["test_examples"] > 0
    assert 0.0 <= report["random_forest"]["accuracy"] <= 1.0
    assert 0.0 <= report["logistic_regression_baseline"]["accuracy"] <= 1.0
    assert report["deterministic_matcher_on_same_seeds"]["total"] > 0
    assert set(report["random_forest"]["feature_importances"].keys()) == set(FEATURE_NAMES)

    assert (tmp_path / "model.skops").exists()
    loaded_model = sio.load(tmp_path / "model.skops", trusted=sio.get_untrusted_types(file=tmp_path / "model.skops"))
    prediction = loaded_model.predict([[0.0, 0.0, 0, 1.0, 1.0, 1.0, 1.0, 1.0, 1000.0, 1000.0]])
    assert prediction[0] in (0, 1)
