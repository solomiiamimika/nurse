// app_mobile/app/(auth)/login.tsx
import React, { useState } from 'react';
import { 
  View, 
  TextInput, 
  Text, 
  Alert, 
  StyleSheet, 
  TouchableOpacity, 
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator 
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import api from '../../src/api/api';

export default function LoginScreen() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!username || !password) {
      Alert.alert('Помилка', 'Введіть логін та пароль');
      return;
    }

    setLoading(true);
    try {
      // POST на /login. 'username' тут може бути як email, так і нікнейм
      const response = await api.post('/auth/api/login', {
        username: username,
        password: password
      });

      const { access_token, user } = response.data;

      // Зберігаємо дані
      await SecureStore.setItemAsync('userToken', access_token);
      await SecureStore.setItemAsync('userInfo', JSON.stringify(user));

      // Перенаправляємо на головну
      router.replace('/(tabs)');

    } catch (error: any) {
      console.log('Login Error:', error);
      const msg = error.response?.data?.msg || 'Невірний логін або пароль';
      Alert.alert('Помилка входу', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1 }}
    >
      <Stack.Screen options={{ title: 'Вхід' }} />
      <View style={styles.container}>
        <Text style={styles.title}>Nurse App</Text>
        <Text style={styles.subtitle}>Вхід у систему</Text>
        
        <View style={styles.form}>
          <Text style={styles.label}>Логін або Email</Text>
          <TextInput
            style={styles.input}
            placeholder="Введіть логін"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
          />
          
          <Text style={styles.label}>Пароль</Text>
          <TextInput
            style={styles.input}
            placeholder="Введіть пароль"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          {loading ? (
             <ActivityIndicator size="large" color="#007AFF" style={{marginVertical: 20}} />
          ) : (
            <TouchableOpacity style={styles.loginBtn} onPress={handleLogin}>
              <Text style={styles.loginBtnText}>Увійти</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity onPress={() => router.push('/(auth)/register')} style={styles.registerLink}>
            <Text style={styles.registerText}>Немає акаунту? Зареєструватися</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 25, backgroundColor: '#fff' },
  title: { fontSize: 36, fontWeight: 'bold', color: '#007AFF', textAlign: 'center', marginBottom: 10 },
  subtitle: { fontSize: 18, color: '#666', textAlign: 'center', marginBottom: 40 },
  form: { width: '100%' },
  label: { marginBottom: 8, color: '#333', fontWeight: '600' },
  input: {
    height: 55,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 20,
    paddingHorizontal: 15,
    borderRadius: 10,
    backgroundColor: '#f8f8f8',
    fontSize: 16
  },
  loginBtn: {
    backgroundColor: '#007AFF',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  loginBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  registerLink: { marginTop: 25, alignItems: 'center' },
  registerText: { color: '#007AFF', fontSize: 16 }
});