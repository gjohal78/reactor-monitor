import { createContext } from "react";

import type { Role, User } from "../api/types";

export interface AuthState {
  user: User | null;
  /** True while restoring a session from a previous page load. */
  loading: boolean;
  /** Set when the session ended by itself (refresh failed), for the login page to explain. */
  expired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  can: (required: Role) => boolean;
}

export const AuthContext = createContext<AuthState | null>(null);
