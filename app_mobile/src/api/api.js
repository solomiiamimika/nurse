// app_mobile/src/api/api.js
import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// 1. Визначаємо базовий URL
// Для Android емулятора це 10.0.2.2, для iOS - localhost.
// ЯКЩО ви тестуєте на реальному телефоні, сюди треба вписати IP вашого комп'ютера (напр. 'http://192.168.1.15:5000/api/auth')
const BASE_URL = Platform.OS === 'android' 
  ? 'http://10.0.2.2:5000/api/auth' 
  : 'http://localhost:5000/api/auth';

const api = axios.create({
  baseURL: 'https://human-me.com',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 2. Інтерсептор (перехоплювач): додає токен до кожного запиту
api.interceptors.request.use(
  async (config) => {
    try {
      const token = await SecureStore.getItemAsync('userToken');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (error) {
      console.log('Error fetching token', error);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 3. (Опціонально) Обробка 401 помилки (якщо токен протух)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response && error.response.status === 401) {
      // Тут можна додати логіку очищення токена і перенаправлення на логін
      await SecureStore.deleteItemAsync('userToken');
    }
    return Promise.reject(error);
  }
);

export default api;