// app_mobile/app/(auth)/register.tsx
import React, { useState } from 'react';
import { 
  View, 
  TextInput, 
  Text, 
  Alert, 
  StyleSheet, 
  TouchableOpacity, 
  ScrollView, 
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import api from '../../src/api/api';

export default function RegisterScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  
  // Стан форми
  const [formData, setFormData] = useState({
    username: '',   // Важливо: це user_name в БД
    full_name: '',  // Важливо: це full_name в БД
    email: '',
    password: '',
    role: 'client'  // Дефолтна роль
  });

  const handleRegister = async () => {
    // Базова валідація
    if (!formData.username || !formData.email || !formData.password) {
      Alert.alert('Помилка', 'Заповніть обов\'язкові поля');
      return;
    }

    setLoading(true);
    try {
      // POST запит на наш новий endpoint
      const response = await api.post('/register', formData);
      
      const { access_token, user } = response.data;
      
      // Зберігаємо сесію
      await SecureStore.setItemAsync('userToken', access_token);
      await SecureStore.setItemAsync('userInfo', JSON.stringify(user));
      
      Alert.alert('Успіх', `Ласкаво просимо, ${user.full_name || user.username}!`);
      
      // Переходимо всередину додатка
      router.replace('/(tabs)');
      
    } catch (error: any) {
      console.log('Reg Error:', error);
      const msg = error.response?.data?.msg || 'Не вдалося зареєструватися';
      // Якщо сервер повернув список помилок validation errors
      const details = error.response?.data?.errors 
        ? '\n' + error.response.data.errors.join('\n') 
        : '';
        
      Alert.alert('Помилка', msg + details);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1 }}
    >
      <Stack.Screen options={{ title: 'Створити акаунт' }} />
      <ScrollView contentContainerStyle={styles.container}>
        
        <Text style={styles.header}>Реєстрація</Text>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Логін (Username)*</Text>
          <TextInput
            style={styles.input}
            placeholder="super_nurse_2024"
            value={formData.username}
            onChangeText={(text) => setFormData({...formData, username: text})}
            autoCapitalize="none"
          />
        </View>
        
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Повне ім'я (Full Name)</Text>
          <TextInput
            style={styles.input}
            placeholder="Іван Іваненко"
            value={formData.full_name}
            onChangeText={(text) => setFormData({...formData, full_name: text})}
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Email*</Text>
          <TextInput
            style={styles.input}
            placeholder="email@example.com"
            value={formData.email}
            onChangeText={(text) => setFormData({...formData, email: text})}
            keyboardType="email-address"
            autoCapitalize="none"
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Пароль*</Text>
          <TextInput
            style={styles.input}
            placeholder="******"
            value={formData.password}
            onChangeText={(text) => setFormData({...formData, password: text})}
            secureTextEntry
          />
        </View>

        {/* Вибір ролі */}
        <Text style={styles.label}>Хто ви?</Text>
        <View style={styles.roleContainer}>
          <TouchableOpacity 
            style={[styles.roleBtn, formData.role === 'client' && styles.roleBtnActive]}
            onPress={() => setFormData({...formData, role: 'client'})}
          >
            <Text style={formData.role === 'client' ? styles.textActive : styles.text}>Я Клієнт</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.roleBtn, formData.role === 'nurse' && styles.roleBtnActive]}
            onPress={() => setFormData({...formData, role: 'nurse'})}
          >
            <Text style={formData.role === 'nurse' ? styles.textActive : styles.text}>Я Медсестра</Text>
          </TouchableOpacity>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color="#007AFF" />
        ) : (
          <TouchableOpacity style={styles.submitBtn} onPress={handleRegister}>
            <Text style={styles.submitBtnText}>Зареєструватися</Text>
          </TouchableOpacity>
        )}
        
        <TouchableOpacity onPress={() => router.push('/(auth)/login')} style={styles.linkContainer}>
           <Text style={styles.linkText}>Вже є акаунт? Увійти</Text>
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
    height: 50,
    borderColor: '#ddd',
    borderWidth: 1,
    paddingHorizontal: 15,
    borderRadius: 8,
    backgroundColor: '#f9f9f9',
    fontSize: 16
  },
  roleContainer: {
    flexDirection: 'row',
    marginBottom: 25,
    marginTop: 5
  },
  roleBtn: {
    flex: 1,
    padding: 15,
    borderWidth: 1,
    borderColor: '#ddd',
    marginRight: 10,
    borderRadius: 8,
    alignItems: 'center',
    backgroundColor: '#f9f9f9'
  },
  roleBtnActive: {
    backgroundColor: '#007AFF',
    borderColor: '#007AFF',
  },
  text: { color: '#333', fontWeight: '500' },
  textActive: { color: 'white', fontWeight: 'bold' },
  submitBtn: {
    backgroundColor: '#007AFF',
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 20,
    marginTop: 10
  },
  submitBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  linkContainer: { alignItems: 'center', padding: 10 },
  linkText: { color: '#007AFF', fontSize: 16 }
});