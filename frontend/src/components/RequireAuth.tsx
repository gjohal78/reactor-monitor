import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import type { Role } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { ROLE_LABEL } from "../auth/roles";
import { Header } from "./Header";

/** Sends signed-out users to the login page. With `role`, also checks the user's role. */
export function RequireAuth({ children, role }: { children: ReactNode; role?: Role }) {
  const { user, loading, can } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (role && !can(role)) {
    return (
      <div className="shell">
        <Header />
        <div />
        <main className="page">
          <p className="notice">
            This page is for {ROLE_LABEL[role].toLowerCase()}s. You're signed in as{" "}
            {ROLE_LABEL[user.role].toLowerCase()}.
          </p>
        </main>
      </div>
    );
  }
  return <>{children}</>;
}
