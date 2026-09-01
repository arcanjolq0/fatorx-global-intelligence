import type {
  ActivityItem,
  ClaimReviewSummary,
  ClaimSummary,
  DashboardSummary,
  EvidenceSummary,
  InvestigationDetail,
  InvestigationSummary,
} from "./types";

export interface IntelligenceDataSource {
  getDashboardSummary(): Promise<DashboardSummary>;
  listInvestigations(): Promise<readonly InvestigationSummary[]>;
  getInvestigationDetail(investigationId: string): Promise<InvestigationDetail | null>;
  listEvidence(investigationId?: string): Promise<readonly EvidenceSummary[]>;
  listClaims(investigationId?: string): Promise<readonly ClaimSummary[]>;
  listFactualReviews(investigationId?: string): Promise<readonly ClaimReviewSummary[]>;
  getRecentActivity(): Promise<readonly ActivityItem[]>;
}
