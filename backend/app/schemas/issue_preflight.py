from pydantic import BaseModel, Field


class PreflightStatement(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)


class PreflightComponent(BaseModel):
    path: str
    description: str
    evidence_ids: list[str] = Field(min_length=1)


class PreflightReport(BaseModel):
    objective: PreflightStatement
    requirements: list[PreflightStatement]
    hard_constraints: list[PreflightStatement]
    affected_components: list[PreflightComponent]
    contract_impacts: list[PreflightStatement]
    acceptance_criteria: list[PreflightStatement]
    test_recommendations: list[PreflightStatement]
    risks: list[PreflightStatement]
    open_questions: list[str]


class PreflightScopeUpdate(BaseModel):
    paths: list[str]
