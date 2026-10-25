from pydantic import BaseModel, Field
from typing import Optional, Literal


class JobRequirement(BaseModel):
    requirement: str = Field(max_length=160)
    jd_evidence: str = Field(min_length=1, max_length=500)
    category: Literal["skills", "experience", "projects", "education", "certifications", "responsibilities"]
    essential: bool = True
    status: Literal["met", "partial", "missing"]
    evidence: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(max_length=180)


class EvidenceField(BaseModel):
    value: Optional[str | list[str]] = None
    evidence: list[str] = Field(default_factory=list)
    status: Literal["supported", "missing", "uncertain"] = "missing"


class ResumeFields(BaseModel):
    name: EvidenceField = Field(default_factory=EvidenceField)
    email: EvidenceField = Field(default_factory=EvidenceField)
    skills: EvidenceField = Field(default_factory=EvidenceField)
    education: EvidenceField = Field(default_factory=EvidenceField)
    experience: EvidenceField = Field(default_factory=EvidenceField)


class AnalysisResult(BaseModel):
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    fields: ResumeFields
    missing_or_uncertain: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    job_requirements: list[JobRequirement] = Field(default_factory=list, max_length=40)
