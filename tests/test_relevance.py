"""Test sullo scoring di rilevanza."""
from backend.app.services.ingest.relevance import infer_technical_level, score_relevance


def test_score_dental_ai_combo_high():
    s = score_relevance(
        title="Deep learning for caries detection on panoramic radiographs",
        abstract="A convolutional neural network achieved high accuracy in detecting dental caries.",
        journal="Journal of Dental Research",
    )
    assert s >= 6.0


def test_score_only_ai_no_dental_low():
    s = score_relevance(
        title="A new transformer architecture for image classification",
        abstract="We propose a vision transformer applied to ImageNet.",
        journal="Nature",
    )
    # niente dental keyword → score abbattuto
    assert s < 4.0


def test_red_flag_penalty():
    s_clean = score_relevance(
        title="AI for dental imaging",
        abstract="Machine learning supports dentists in dental imaging.",
        journal="JADA",
    )
    s_bad = score_relevance(
        title="AI for dental imaging",
        abstract="Our model has 100% accuracy and will replace the dentist completely.",
        journal="JADA",
    )
    assert s_bad < s_clean


def test_technical_level_high():
    lvl = infer_technical_level(
        title="U-Net based segmentation of CBCT scans with Dice coefficient evaluation",
        abstract="Pre-trained backbone, IoU and AUC reported, hyperparameter tuning via ensemble.",
    )
    assert lvl == "high"


def test_technical_level_low():
    lvl = infer_technical_level(
        title="Come l'AI aiuta i dentisti",
        abstract="Una panoramica per pazienti su come l'AI viene usata nel workflow clinico.",
    )
    assert lvl == "low"
