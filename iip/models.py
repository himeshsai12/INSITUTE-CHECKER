"""Validated data contracts. Missing data is None, never an invented zero."""
from datetime import date
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class Status(StrEnum):
    DEMO = "Demo"
    UNVERIFIED = "Unverified"
    SELF_REPORTED = "Self-reported"
    VERIFIED = "Verified"


class SourceType(StrEnum):
    GOVERNMENT = "Government / regulator"
    UNIVERSITY = "University"
    INSTITUTION = "Institution"
    PUBLIC_RECORD = "Public record"
    INTERNAL = "Internal diligence"
    WEB = "Web discovery"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class Evidence(Record):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType = SourceType.WEB
    status: Status = Status.UNVERIFIED
    url: str | None = None
    observed_on: date
    published_on: date | None = None
    valid_until: date | None = None
    period: str = "Not specified"
    excerpt: str = ""
    reviewer: str | None = None
    reviewed_on: date | None = None
    review_note: str = ""

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value:
            parsed = urlparse(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Source URL must be a public http(s) URL without credentials.")
        return value or None

    @model_validator(mode="after")
    def verify_review(self):
        if self.status == Status.VERIFIED and not (self.reviewer and self.reviewed_on and self.review_note.strip()):
            raise ValueError("Verified evidence requires reviewer, review date and review note.")
        return self


class Metric(Record):
    value: float | None = Field(default=None, ge=0)
    evidence_id: str | None = None

    @model_validator(mode="after")
    def require_evidence(self):
        if self.value is not None and not self.evidence_id:
            raise ValueError("Every populated metric needs an evidence_id.")
        return self


class Admission(Record):
    year: str = Field(pattern=r"^\d{4}-\d{2}$")
    intake: int = Field(ge=0)
    registered: int | None = Field(default=None, ge=0)
    claimed: int | None = Field(default=None, ge=0)
    intake_evidence_id: str
    registration_evidence_id: str | None = None
    claim_evidence_id: str | None = None

    @model_validator(mode="after")
    def references(self):
        if int(self.year[-2:]) != (int(self.year[:4])+1) % 100:
            raise ValueError("Academic year must span consecutive years, such as 2025-26.")
        if self.registered is not None and not self.registration_evidence_id:
            raise ValueError("Registered admissions require registration evidence.")
        if self.claimed is not None and not self.claim_evidence_id:
            raise ValueError("Claimed admissions require claim evidence.")
        return self


class Placement(Record):
    year: int = Field(ge=1900, le=2200)
    eligible: int = Field(ge=0)
    placed: int = Field(ge=0)
    batch_size: int | None = Field(default=None, ge=0)
    claimed_percent: float | None = Field(default=None, ge=0, le=100)
    highest_lpa: float | None = Field(default=None, ge=0)
    average_lpa: float | None = Field(default=None, ge=0)
    median_lpa: float | None = Field(default=None, ge=0)
    evidence_id: str
    claim_evidence_id: str | None = None

    @model_validator(mode="after")
    def consistency(self):
        if self.placed > self.eligible:
            raise ValueError("Students placed cannot exceed eligible students.")
        if self.batch_size is not None and self.eligible > self.batch_size:
            raise ValueError("Eligible students cannot exceed the batch size.")
        if self.claimed_percent is not None and not self.claim_evidence_id:
            raise ValueError("A placement claim requires its own source.")
        return self


class Course(Record):
    name: str
    level: str
    year: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    intake: int = Field(ge=0)
    admissions: int | None = Field(default=None, ge=0)
    annual_fee: float | None = Field(default=None, ge=0)
    change: str = "Continuing"
    evidence_id: str

    @field_validator("year")
    @classmethod
    def academic_year(cls, value):
        if value and int(value[-2:]) != (int(value[:4]) + 1) % 100:
            raise ValueError("Academic year must span consecutive years.")
        return value


class Accreditation(Record):
    body: str
    outcome: str
    category: str = "Institution"
    year: int = Field(ge=1900, le=2200)
    valid_until: date | None = None
    evidence_id: str


class Recruiter(Record):
    name: str
    sector: str
    year: int | None = Field(default=None, ge=1900, le=2200)
    offers: int = Field(ge=0)
    repeat: bool = False
    location: str = "Not disclosed"
    internship: bool = False
    international: bool | None = None
    evidence_id: str


class LegalRecord(Record):
    title: str
    stage: str = Field(pattern=r"^(Complaint|FIR|Charge|Prosecution|Conviction|Acquittal|Civil dispute|Regulatory notice|Insolvency proceeding)$")
    date: date
    reference: str
    description: str
    evidence_id: str


class Promoter(Record):
    organisation: str = "Not disclosed"
    established: int | None = None
    names: list[str] = Field(default_factory=list)
    board: list[str] = Field(default_factory=list)
    other_institutions: list[str] = Field(default_factory=list)
    previous_institutions: list[str] = Field(default_factory=list)
    businesses: list[str] = Field(default_factory=list)
    evidence_id: str | None = None
    records: list[LegalRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_required(self):
        if (self.organisation != "Not disclosed" or self.names or self.board or self.other_institutions or self.previous_institutions or self.businesses or self.established) and not self.evidence_id:
            raise ValueError("Promoter identity and associations require an evidence reference.")
        return self


class Institution(Record):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=3)
    city: str
    state: str
    university: str = "Not disclosed"
    ownership: str = "Not disclosed"
    established: int | None = None
    aishe_code: str | None = None
    website: str | None = None
    campus_status: str = "Not established"
    identity_evidence_id: str | None = None
    demo: bool = False
    admissions: list[Admission] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)
    courses: list[Course] = Field(default_factory=list)
    accreditations: list[Accreditation] = Field(default_factory=list)
    recruiters: list[Recruiter] = Field(default_factory=list)
    campus: dict[str, Metric] = Field(default_factory=dict)
    commercial: dict[str, Metric] = Field(default_factory=dict)
    promoter: Promoter = Field(default_factory=Promoter)
    evidence: list[Evidence] = Field(default_factory=list)

    _safe_website = field_validator("website")(Evidence.safe_url.__func__)

    @model_validator(mode="after")
    def validate_references(self):
        ids = {e.id for e in self.evidence}
        if len(ids) != len(self.evidence):
            raise ValueError("Duplicate evidence IDs.")
        refs = [self.identity_evidence_id, self.promoter.evidence_id]
        for row in self.admissions:
            refs.extend([row.intake_evidence_id, row.registration_evidence_id, row.claim_evidence_id])
        for row in self.placements:
            refs.extend([row.evidence_id, row.claim_evidence_id])
        for row in [*self.courses, *self.accreditations, *self.recruiters, *self.promoter.records]:
            refs.append(row.evidence_id)
        refs.extend(m.evidence_id for m in [*self.campus.values(), *self.commercial.values()])
        missing = set(filter(None, refs)) - ids
        if missing:
            raise ValueError(f"Missing evidence references: {', '.join(sorted(missing))}")
        if not self.demo and any(e.status == Status.DEMO for e in self.evidence):
            raise ValueError("Demo evidence cannot be used in a real institution profile.")
        if self.demo and any(e.status != Status.DEMO for e in self.evidence):
            raise ValueError("Demo profiles must retain Demo status on all evidence.")
        for field in [self.admissions, self.placements]:
            if len({r.year for r in field}) != len(field):
                raise ValueError("Duplicate academic years in a time series.")
        if len({(c.name.casefold(), c.level, c.year) for c in self.courses}) != len(self.courses):
            raise ValueError("Duplicate course, level and academic year.")
        for key in ["pass_percent", "graduation_percent", "attendance_percent", "dropout_percent", "faculty_attrition_percent", "progression_percent"]:
            metric = self.campus.get(key)
            if metric and metric.value is not None and metric.value > 100:
                raise ValueError(f"{key} must be a percentage between 0 and 100.")
        for key in ["collection_percent", "scholarship_percent", "discount_percent", "refund_percent"]:
            metric = self.commercial.get(key)
            if metric and metric.value is not None and metric.value > 100:
                raise ValueError(f"{key} must be a percentage between 0 and 100.")
        return self

    def source(self, evidence_id):
        return next((e for e in self.evidence if e.id == evidence_id), None)

    def value(self, section, key):
        metric = getattr(self, section).get(key)
        return metric.value if metric else None

    @property
    def latest_admission(self):
        return max(self.admissions, key=lambda r: r.year) if self.admissions else None

    @property
    def latest_placement(self):
        return max(self.placements, key=lambda r: r.year) if self.placements else None
