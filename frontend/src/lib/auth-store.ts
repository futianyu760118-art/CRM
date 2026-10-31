'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { api } from '@/lib/api';
import type { CurrentUser, TokenPair } from '@/types';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUser | null;
  loading: boolean;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setUser: (user: CurrentUser | null) => void;
  login: (username: string, password: string) => Promise<CurrentUser>;
  loadUser: () => Promise<CurrentUser | null>;
  logout: () => Promise<void>;
  clear: () => void;
  hasPermission: (code: string) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      loading: false,

      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),

      setUser: (user) => set({ user }),

      login: async (username, password) => {
        set({ loading: true });
        try {
          const tokens = await api.post<TokenPair>(
            '/auth/login',
            { username, password },
            { auth: false },
          );
          set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
          const user = await api.get<CurrentUser>('/auth/me');
          set({ user });
          return user;
        } finally {
          set({ loading: false });
        }
      },

      loadUser: async () => {
        if (!get().accessToken) return null;
        try {
          const user = await api.get<CurrentUser>('/auth/me');
          set({ user });
          return user;
        } catch {
          get().clear();
          return null;
        }
      },

      logout: async () => {
        const { refreshToken } = get();
        try {
          await api.post('/auth/logout', { refresh_token: refreshToken });
        } catch {
          // 忽略登出异常
        }
        get().clear();
      },

      clear: () => set({ accessToken: null, refreshToken: null, user: null }),

      hasPermission: (code) => {
        const user = get().user;
        if (!user) return false;
        if (user.is_superuser || user.permissions.includes('*')) return true;
        return user.permissions.includes(code);
      },
    }),
    {
      name: 'crm-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    },
  ),
);
