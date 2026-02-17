// app_mobile/app/(tabs)/index.tsx
import React, { useCallback, useState } from 'react';
import { Image, StyleSheet, View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Alert } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function HomeScreen() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null); // null = ще перевіряємо
  const [userInfo, setUserInfo] = useState<any>(null);

  // Ця функція запускається щоразу, коли ви відкриваєте (фокусуєте) цей екран
  useFocusEffect(
    useCallback(() => {
      checkAuth();
    }, [])
  );

  const checkAuth = async () => {
    try {
      const token = await SecureStore.getItemAsync('userToken');
      const userStr = await SecureStore.getItemAsync('userInfo');
      
      if (token) {
        setIsAuthenticated(true);
        if (userStr) setUserInfo(JSON.parse(userStr));
      } else {
        setIsAuthenticated(false);
        setUserInfo(null);
      }
    } catch (e) {
      console.log(e);
      setIsAuthenticated(false);
    }
  };

  const handleLogout = async () => {
    await SecureStore.deleteItemAsync('userToken');
    await SecureStore.deleteItemAsync('userInfo');
    setIsAuthenticated(false);
    Alert.alert('Вихід', 'Ви успішно вийшли з системи');
  };

  // 1. Стан завантаження (поки перевіряємо токен)
  if (isAuthenticated === null) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  // 2. Вигляд для ГОСТЯ (не залогінений)
  if (!isAuthenticated) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.guestContent}>
          <Image 
            source={require('../../assets/images/react-logo.png')} 
            style={styles.logo} 
          />
          <Text style={styles.title}>Вітаємо в Nurse App!</Text>
          <Text style={styles.subtitle}>
            Знайдіть професійну медсестру поруч із вами або надавайте послуги самостійно.
          </Text>
          
          <View style={styles.buttonContainer}>
            <TouchableOpacity 
              style={[styles.btn, styles.primaryBtn]} 
              onPress={() => router.push('/(auth)/login')} // Перехід на Логін
            >
              <Text style={styles.primaryBtnText}>Увійти</Text>
            </TouchableOpacity>

            <TouchableOpacity 
              style={[styles.btn, styles.secondaryBtn]} 
              onPress={() => router.push('/(auth)/register')} // Перехід на Реєстрацію
            >
              <Text style={styles.secondaryBtnText}>Зареєструватися</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  // 3. Вигляд для ЮЗЕРА (залогінений)
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={{ paddingBottom: 20 }}>
        <View style={styles.header}>
          <Text style={styles.welcomeText}>Привіт, {userInfo?.full_name || 'Користувач'}!</Text>
          <TouchableOpacity onPress={handleLogout}>
            <Text style={{ color: 'red' }}>Вийти</Text>
          </TouchableOpacity>
        </View>

        {/* Тут буде ваш список медсестер */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Ваші майбутні візити</Text>
          <Text style={{ color: '#666', marginTop: 5 }}>Поки що немає записів.</Text>
          <TouchableOpacity 
            style={{ marginTop: 15 }}
            onPress={() => router.push('/(tabs)/explore')}
          >
            <Text style={{ color: '#007AFF', fontWeight: 'bold' }}>Знайти медсестру →</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Популярні послуги</Text>
          {/* Мок-картки послуг */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }}>
            {['Крапельниці', 'Уколи', 'Перев\'язки', 'Догляд'].map((item, index) => (
              <View key={index} style={styles.serviceCard}>
                <Text style={{ fontWeight: '600' }}>{item}</Text>
              </View>
            ))}
          </ScrollView>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  
  // Стилі для гостя
  guestContent: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  logo: { width: 100, height: 100, marginBottom: 20, tintColor: '#007AFF' },
  title: { fontSize: 28, fontWeight: 'bold', marginBottom: 10, textAlign: 'center' },
  subtitle: { fontSize: 16, color: '#666', textAlign: 'center', marginBottom: 40, lineHeight: 22 },
  buttonContainer: { width: '100%', gap: 15 },
  btn: { padding: 16, borderRadius: 12, alignItems: 'center', width: '100%' },
  primaryBtn: { backgroundColor: '#007AFF' },
  secondaryBtn: { backgroundColor: 'transparent', borderWidth: 2, borderColor: '#007AFF' },
  primaryBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  secondaryBtnText: { color: '#007AFF', fontSize: 18, fontWeight: 'bold' },

  // Стилі для юзера
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20 },
  welcomeText: { fontSize: 22, fontWeight: 'bold' },
  card: { backgroundColor: 'white', margin: 20, padding: 20, borderRadius: 15, shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 5, elevation: 3 },
  cardTitle: { fontSize: 18, fontWeight: 'bold' },
  section: { paddingHorizontal: 20, marginTop: 10 },
  sectionTitle: { fontSize: 20, fontWeight: 'bold', marginBottom: 10 },
  serviceCard: { backgroundColor: 'white', width: 120, height: 80, justifyContent: 'center', alignItems: 'center', marginRight: 10, borderRadius: 10 }
});