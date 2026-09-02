import type { IconName } from "../icons/Icon";
import { Icon } from "../icons/Icon";
import { Card } from "../ui";

export function StatCard({
  detail,
  icon,
  label,
  tone = "primary",
  value,
}: {
  readonly detail: string;
  readonly icon: IconName;
  readonly label: string;
  readonly tone?: "primary" | "success" | "violet" | "warning";
  readonly value: number;
}) {
  return (
    <Card className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__heading">
        <p>{label}</p>
        <span className="stat-card__icon">
          <Icon name={icon} />
        </span>
      </div>
      <strong>{value.toLocaleString("pt-BR")}</strong>
      <span>{detail}</span>
    </Card>
  );
}
