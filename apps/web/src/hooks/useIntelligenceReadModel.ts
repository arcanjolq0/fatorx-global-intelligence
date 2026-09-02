import { useCallback, useEffect, useState } from "react";

import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import type {
  ClaimReviewSummary,
  ClaimSummary,
  EvidenceSummary,
  InvestigationSummary,
} from "../data/types";

export type IntelligenceReadModelState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | {
      readonly status: "ready";
      readonly claims: readonly ClaimSummary[];
      readonly evidence: readonly EvidenceSummary[];
      readonly investigations: readonly InvestigationSummary[];
      readonly reviews: readonly ClaimReviewSummary[];
    };

export function useIntelligenceReadModel(dataSource: IntelligenceDataSource) {
  const [state, setState] = useState<IntelligenceReadModelState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.listInvestigations(),
      dataSource.listEvidence(),
      dataSource.listClaims(),
      dataSource.listFactualReviews(),
    ]).then(
      ([investigations, evidence, claims, reviews]) => {
        if (isCurrent) setState({ status: "ready", investigations, evidence, claims, reviews });
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setRetryVersion((current) => current + 1);
  }, []);

  return { retry, state } as const;
}
