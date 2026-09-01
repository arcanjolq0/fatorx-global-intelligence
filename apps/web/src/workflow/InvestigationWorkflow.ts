import type { EntityCandidate, InvestigationLifecycleStatus } from "../data/types";

export interface SearchEntityCandidatesCommand {
  readonly identifier: string;
}

export interface EntityCandidateSearchResult {
  readonly candidates: readonly EntityCandidate[];
  readonly normalizedIdentifier: string;
  readonly searchReference: string;
}

export interface CreateInvestigationCommand {
  readonly candidateId: string;
  readonly searchReference: string;
}

export interface CreatedInvestigation {
  readonly investigationId: string;
  readonly lifecycleStatus: Extract<
    InvestigationLifecycleStatus,
    "WAITING_FOR_ENTITY_CONFIRMATION"
  >;
}

export interface ConfirmEntityCommand {
  readonly candidateId: string;
  readonly investigationId: string;
}

export interface ConfirmedEntityResult {
  readonly entityId: string;
  readonly investigationId: string;
}

export interface InvestigationWorkflow {
  searchEntityCandidates(
    command: SearchEntityCandidatesCommand,
  ): Promise<EntityCandidateSearchResult>;
  createInvestigation(command: CreateInvestigationCommand): Promise<CreatedInvestigation>;
  confirmEntity(command: ConfirmEntityCommand): Promise<ConfirmedEntityResult>;
}
