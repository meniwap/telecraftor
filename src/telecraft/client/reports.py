from __future__ import annotations

from typing import Any

from telecraft.tl.generated.types import (
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonFake,
    InputReportReasonGeoIrrelevant,
    InputReportReasonIllegalDrugs,
    InputReportReasonOther,
    InputReportReasonPersonalDetails,
    InputReportReasonPornography,
    InputReportReasonSpam,
    InputReportReasonViolence,
)


class ReportReasonBuilder:
    @staticmethod
    def spam() -> Any:
        return InputReportReasonSpam()

    @staticmethod
    def violence() -> Any:
        return InputReportReasonViolence()

    @staticmethod
    def pornography() -> Any:
        return InputReportReasonPornography()

    @staticmethod
    def child_abuse() -> Any:
        return InputReportReasonChildAbuse()

    @staticmethod
    def copyright() -> Any:
        return InputReportReasonCopyright()

    @staticmethod
    def illegal_drugs() -> Any:
        return InputReportReasonIllegalDrugs()

    @staticmethod
    def personal_details() -> Any:
        return InputReportReasonPersonalDetails()

    @staticmethod
    def fake() -> Any:
        return InputReportReasonFake()

    @staticmethod
    def geo_irrelevant() -> Any:
        return InputReportReasonGeoIrrelevant()

    @staticmethod
    def other(text: str = "") -> Any:
        _ = text
        return InputReportReasonOther()
