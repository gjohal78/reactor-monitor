import type { Role } from "../api/types";

/**
 * Mirrors backend/app/auth/roles.py. Used only to decide what to show: the backend
 * enforces every permission itself, so hiding a button here is a convenience, not a
 * security boundary.
 */
const RANK: Record<Role, number> = { viewer: 0, operator: 1, supervisor: 2 };

export function roleAllows(role: Role, required: Role): boolean {
  return RANK[role] >= RANK[required];
}

export const ROLE_LABEL: Record<Role, string> = {
  viewer: "Viewer",
  operator: "Operator",
  supervisor: "Supervisor",
};
