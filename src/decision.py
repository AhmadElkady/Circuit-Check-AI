
"""Inspection decision engine for CircuitCheck AI."""

from __future__ import annotations

from dataclasses import dataclass

from config import (
    CLASSES,
    SEVERITY,
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_REVIEW,
)

from post_processing import Detection, PostprocessResult


@dataclass(frozen=True)
class DecisionResult:
    """Final inspection decision and its supporting evidence."""

    status: str
    detections: list[Detection]
    review_candidates: list[Detection]
    reasons: list[str]
    inspection_complete: bool

    @property
    def total_defects(self) -> int:
        return len(self.detections)

    @property
    def total_review_candidates(self) -> int:
        return len(self.review_candidates)


def decide(
    result: PostprocessResult,
    *,
    inspection_complete: bool = True,
) -> DecisionResult:
    """
    Decide whether a PCB passes, fails, or requires manual review.

    Rules:
    1. Confirmed defects -> FAIL.
    2. Incomplete inspection -> REVIEW unless a confirmed defect exists.
    3. Borderline detections -> REVIEW.
    4. No defects or review candidates -> PASS.
    """

    detections = result.detections
    review_candidates = result.review_candidates

    reasons = []

    # Ensure every detected class is recognized.
    for detection in detections + review_candidates:
        if detection.class_name not in CLASSES:
            raise ValueError(
                f"Unknown defect class: {detection.class_name}"
            )

        if detection.class_name not in SEVERITY:
            raise ValueError(
                f"Missing severity for: {detection.class_name}"
            )

    # Confirmed defects take priority.
    if detections:
        for detection in detections:
            severity = SEVERITY[detection.class_name]

            reasons.append(
                f"{detection.class_name} detected "
                f"(severity: {severity}, "
                f"confidence: {detection.confidence:.2f})"
            )

        return DecisionResult(
            status=STATUS_FAIL,
            detections=detections,
            review_candidates=review_candidates,
            reasons=reasons,
            inspection_complete=inspection_complete,
        )

    # An incomplete inspection cannot receive PASS.
    if not inspection_complete:
        reasons.append("Inspection was not completed successfully.")

    # Borderline detections need human verification.
    if review_candidates:
        reasons.append(
            f"{len(review_candidates)} borderline detection(s) "
            "require manual verification."
        )

    if not inspection_complete or review_candidates:
        return DecisionResult(
            status=STATUS_REVIEW,
            detections=detections,
            review_candidates=review_candidates,
            reasons=reasons,
            inspection_complete=inspection_complete,
        )

    # No confirmed defects and no uncertain candidates.
    reasons.append("No PCB defects detected.")

    return DecisionResult(
        status=STATUS_PASS,
        detections=detections,
        review_candidates=review_candidates,
        reasons=reasons,
        inspection_complete=True,
    )
