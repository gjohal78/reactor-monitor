import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { clearTokens, hasSession, onSessionExpired, setTokens } from "../api/client";
import { getMe, login as loginRequest } from "../api/endpoints";
import type { Role, User } from "../api/types";
import { AuthContext } from "./context";
import { roleAllows } from "./roles";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(hasSession());
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    // Restore the session after a reload: the tokens are in sessionStorage.
    if (!hasSession()) return;
    getMe()
      .then(setUser)
      .catch(() => {
        clearTokens();
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(null);
        setExpired(true);
      }),
    [],
  );

  const login = useCallback(async (username: string, password: string) => {
    setTokens(await loginRequest(username, password));
    setUser(await getMe());
    setExpired(false);
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const can = useCallback((required: Role) => user !== null && roleAllows(user.role, required), [user]);

  const value = useMemo(
    () => ({ user, loading, expired, login, logout, can }),
    [user, loading, expired, login, logout, can],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
