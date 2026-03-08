import React, { useState } from 'react';
import {
  View, TextInput, Text, Alert, StyleSheet,
  TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import * as SecureStore from 'expo-secure-store';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';

export default function LoginScreen() {
  const router = useRouter();
  const { login } = useAuth();
  const { t } = useI18n();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    try {
      const result = await WebBrowser.openAuthSessionAsync(
        'https://human-me.com/auth/google',
        'appmobile://'
      );
      if (result.type === 'success' && result.url) {
        const url = new URL(result.url);
        const token = url.searchParams.get('token');
        if (token) {
          await SecureStore.setItemAsync('userToken', token);
          // Fetch user info with the new token
          const res = await api.get('/auth/api/me', {
            headers: { Authorization: `Bearer ${token}` },
          });
          const user = res.data;
          await SecureStore.setItemAsync('userInfo', JSON.stringify(user));
          // Reload to trigger auth state change
          router.replace('/');
        }
      }
    } catch (error: any) {
      Alert.alert(t('error'), 'Google sign-in failed. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!username || !password) {
      Alert.alert(t('error'), t('fillLoginPassword'));
      return;
    }
    setLoading(true);
    try {
      await login(username, password);
    } catch (error: any) {
      const msg = error.response?.data?.msg || 'Wrong login or password';
      Alert.alert('Login Error', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
      <Stack.Screen options={{ title: t('signIn') }} />
      <View style={styles.container}>
        <Text style={styles.title}>Nurse App</Text>
        <Text style={styles.subtitle}>{t('login')}</Text>

        <View style={styles.form}>
          <Text style={styles.label}>{t('usernameOrEmail')}</Text>
          <TextInput
            style={styles.input}
            placeholder={t('enterLogin')}
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
          />

          <Text style={styles.label}>{t('password')}</Text>
          <TextInput
            style={styles.input}
            placeholder={t('enterPassword')}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          {loading ? (
            <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 20 }} />
          ) : (
            <TouchableOpacity style={styles.loginBtn} onPress={handleLogin}>
              <Text style={styles.loginBtnText}>{t('signIn')}</Text>
            </TouchableOpacity>
          )}

          {/* Separator */}
          <View style={styles.separator}>
            <View style={styles.separatorLine} />
            <Text style={styles.separatorText}>{t('or')}</Text>
            <View style={styles.separatorLine} />
          </View>

          {/* Google Sign In */}
          {googleLoading ? (
            <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 20 }} />
          ) : (
            <TouchableOpacity style={styles.googleBtn} onPress={handleGoogleLogin}>
              <Text style={styles.googleBtnIcon}>G</Text>
              <Text style={styles.googleBtnText}>{t('signInGoogle')}</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity onPress={() => router.push('/(auth)/register')} style={styles.registerLink}>
            <Text style={styles.registerText}>{t('noAccount')} {t('signUp')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 25, backgroundColor: '#fff' },
  title: { fontSize: 36, fontWeight: 'bold', color: '#3f4a36', textAlign: 'center', marginBottom: 10 },
  subtitle: { fontSize: 18, color: '#666', textAlign: 'center', marginBottom: 40 },
  form: { width: '100%' },
  label: { marginBottom: 8, color: '#333', fontWeight: '600' },
  input: {
    height: 55, borderColor: '#e1e1e1', borderWidth: 1, marginBottom: 20,
    paddingHorizontal: 15, borderRadius: 10, backgroundColor: '#f8f8f8', fontSize: 16,
  },
  loginBtn: {
    backgroundColor: '#3f4a36', padding: 16, borderRadius: 10, alignItems: 'center',
    marginTop: 10, shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1, shadowRadius: 4, elevation: 2,
  },
  loginBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  separator: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 20,
  },
  separatorLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#e1e1e1',
  },
  separatorText: {
    marginHorizontal: 12,
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '500',
  },
  googleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: '#e1e1e1',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
    gap: 10,
  },
  googleBtnIcon: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#4285F4',
  },
  googleBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  registerLink: { marginTop: 25, alignItems: 'center' },
  registerText: { color: '#3f4a36', fontSize: 16 },
});
