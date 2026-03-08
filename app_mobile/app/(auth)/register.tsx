import React, { useState } from 'react';
import {
  View, TextInput, Text, Alert, StyleSheet, TouchableOpacity,
  ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';

export default function RegisterScreen() {
  const router = useRouter();
  const { register } = useAuth();
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);

  const [formData, setFormData] = useState({
    username: '',
    full_name: '',
    email: '',
    password: '',
    role: 'client' as 'client' | 'provider',
  });

  const handleRegister = async () => {
    if (!formData.username || !formData.email || !formData.password) {
      Alert.alert(t('error'), t('fillRequiredFields'));
      return;
    }
    setLoading(true);
    try {
      await register(formData);
    } catch (error: any) {
      const msg = error.response?.data?.msg || 'Registration failed';
      let details = '';
      if (error.response?.data?.errors) {
        const errs = error.response.data.errors;
        details = Array.isArray(errs) ? '\n' + errs.join('\n') : '\n' + JSON.stringify(errs);
      }
      Alert.alert(t('error'), msg + details);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
      <Stack.Screen options={{ title: t('signUp') }} />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.header}>{t('createAccount')}</Text>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>{t('username')} *</Text>
          <TextInput
            style={styles.input} placeholder="username"
            value={formData.username}
            onChangeText={(t) => setFormData({ ...formData, username: t })}
            autoCapitalize="none"
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>{t('fullName')}</Text>
          <TextInput
            style={styles.input} placeholder="John Smith"
            value={formData.full_name}
            onChangeText={(t) => setFormData({ ...formData, full_name: t })}
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>{t('email')} *</Text>
          <TextInput
            style={styles.input} placeholder="email@example.com"
            value={formData.email}
            onChangeText={(t) => setFormData({ ...formData, email: t })}
            keyboardType="email-address" autoCapitalize="none"
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>{t('password')} *</Text>
          <TextInput
            style={styles.input} placeholder="******"
            value={formData.password}
            onChangeText={(t) => setFormData({ ...formData, password: t })}
            secureTextEntry
          />
        </View>

        <Text style={styles.label}>{t('iAm')}</Text>
        <View style={styles.roleContainer}>
          <TouchableOpacity
            style={[styles.roleBtn, formData.role === 'client' && styles.roleBtnActive]}
            onPress={() => setFormData({ ...formData, role: 'client' })}
          >
            <Text style={formData.role === 'client' ? styles.textActive : styles.text}>{t('client')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.roleBtn, formData.role === 'provider' && styles.roleBtnActive]}
            onPress={() => setFormData({ ...formData, role: 'provider' })}
          >
            <Text style={formData.role === 'provider' ? styles.textActive : styles.text}>{t('provider')}</Text>
          </TouchableOpacity>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color="#3f4a36" />
        ) : (
          <TouchableOpacity style={styles.submitBtn} onPress={handleRegister}>
            <Text style={styles.submitBtnText}>{t('signUp')}</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity onPress={() => router.push('/(auth)/login')} style={styles.linkContainer}>
          <Text style={styles.linkText}>{t('hasAccount')} {t('signIn')}</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, backgroundColor: '#fff', justifyContent: 'center' },
  header: { fontSize: 28, fontWeight: 'bold', marginBottom: 30, textAlign: 'center', color: '#333' },
  inputGroup: { marginBottom: 15 },
  label: { marginBottom: 5, color: '#666', fontWeight: '500' },
  input: {
    height: 50, borderColor: '#ddd', borderWidth: 1, paddingHorizontal: 15,
    borderRadius: 8, backgroundColor: '#f9f9f9', fontSize: 16,
  },
  roleContainer: { flexDirection: 'row', marginBottom: 25, marginTop: 5, gap: 10 },
  roleBtn: {
    flex: 1, padding: 15, borderWidth: 1, borderColor: '#ddd',
    borderRadius: 8, alignItems: 'center', backgroundColor: '#f9f9f9',
  },
  roleBtnActive: { backgroundColor: '#3f4a36', borderColor: '#3f4a36' },
  text: { color: '#333', fontWeight: '500' },
  textActive: { color: 'white', fontWeight: 'bold' },
  submitBtn: {
    backgroundColor: '#3f4a36', padding: 16, borderRadius: 8,
    alignItems: 'center', marginBottom: 20, marginTop: 10,
  },
  submitBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  linkContainer: { alignItems: 'center', padding: 10 },
  linkText: { color: '#3f4a36', fontSize: 16 },
});
