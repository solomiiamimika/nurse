import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as SecureStore from 'expo-secure-store';
import { useRouter, useSegments } from 'expo-router';
import api from '../src/api/api';

export interface UserInfo {
  id: number;
  username: string;
  email?: string;
  full_name?: string;
  role: 'client' | 'provider';
  photo?: string | null;
}

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (user: UserInfo) => Promise<void>;
}

interface RegisterData {
  username: string;
  email: string;
  password: string;
  full_name?: string;
  role: 'client' | 'provider';
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const router = useRouter();
  const segments = useSegments();

  // Load stored auth on mount
  useEffect(() => {
    (async () => {
      try {
        const token = await SecureStore.getItemAsync('userToken');
        const userStr = await SecureStore.getItemAsync('userInfo');
        if (token && userStr) {
          const user = JSON.parse(userStr) as UserInfo;
          setState({ token, user, isLoading: false, isAuthenticated: true });
        } else {
          setState(s => ({ ...s, isLoading: false }));
        }
      } catch {
        setState(s => ({ ...s, isLoading: false }));
      }
    })();
  }, []);

  // Route protection
  useEffect(() => {
    if (state.isLoading) return;

    const inAuth = segments[0] === '(auth)';
    const inClient = segments[0] === '(client-tabs)';
    const inProvider = segments[0] === '(provider-tabs)';

    if (!state.isAuthenticated && !inAuth) {
      router.replace('/(auth)/login');
    } else if (state.isAuthenticated && inAuth) {
      const target = state.user?.role === 'provider' ? '/(provider-tabs)' : '/(client-tabs)';
      router.replace(target as any);
    }
  }, [state.isAuthenticated, state.isLoading, segments]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await api.post('/auth/api/login', { username, password });
    const { access_token, user } = response.data;

    await SecureStore.setItemAsync('userToken', access_token);
    await SecureStore.setItemAsync('userInfo', JSON.stringify(user));

    setState({ token: access_token, user, isLoading: false, isAuthenticated: true });
  }, []);

  const register = useCallback(async (data: RegisterData) => {
    const response = await api.post('/auth/api/register', data);
    const { access_token, user } = response.data;

    await SecureStore.setItemAsync('userToken', access_token);
    await SecureStore.setItemAsync('userInfo', JSON.stringify(user));

    setState({ token: access_token, user, isLoading: false, isAuthenticated: true });
  }, []);

  const logout = useCallback(async () => {
    await SecureStore.deleteItemAsync('userToken');
    await SecureStore.deleteItemAsync('userInfo');
    setState({ token: null, user: null, isLoading: false, isAuthenticated: false });
  }, []);

  const updateUser = useCallback(async (user: UserInfo) => {
    await SecureStore.setItemAsync('userInfo', JSON.stringify(user));
    setState(s => ({ ...s, user }));
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}
