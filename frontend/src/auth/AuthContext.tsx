import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setToken, getToken } from "../api/client";
import type { Profile, UserPrivate } from "../api/types";

interface AuthState {
  user: UserPrivate | null;
  profile: Profile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<Profile | null>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPrivate | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSession = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setProfile(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      try {
        setProfile(await api.myProfile());
      } catch {
        setProfile(null); // 404 until they complete onboarding
      }
    } catch {
      setToken(null);
      setUser(null);
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      setLoading(true);
      await loadSession();
    },
    [loadSession],
  );

  const register = useCallback(
    async (data: { email: string; password: string; first_name: string; last_name: string }) => {
      const { access_token } = await api.register(data);
      setToken(access_token);
      setLoading(true);
      await loadSession();
    },
    [loadSession],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setProfile(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const fresh = await api.myProfile();
      setProfile(fresh);
      return fresh;
    } catch {
      setProfile(null);
      return null;
    }
  }, []);

  const value = useMemo(
    () => ({ user, profile, loading, login, register, logout, refreshProfile }),
    [user, profile, loading, login, register, logout, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
