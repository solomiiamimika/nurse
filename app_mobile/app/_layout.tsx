import React, { useEffect } from 'react';
import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { I18nProvider } from '@/contexts/I18nContext';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

function NotificationSetup() {
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      import('../hooks/useNotifications').then(m => m.registerForPushNotifications?.());
    }
  }, [isAuthenticated]);

  return null;
}

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <AuthProvider>
      <I18nProvider>
      <NotificationSetup />
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="(client-tabs)" />
          <Stack.Screen name="(provider-tabs)" />
          <Stack.Screen name="provider/[providerId]" options={{ headerShown: true, title: '' }} />
          <Stack.Screen name="booking/[providerId]" options={{ headerShown: true, title: 'Booking' }} />
          <Stack.Screen name="chat/[userId]" options={{ headerShown: true, title: 'Chat' }} />
          <Stack.Screen name="create-request" options={{ presentation: 'modal', headerShown: true, title: 'New Request' }} />
          <Stack.Screen name="payment/[appointmentId]" options={{ headerShown: true, title: 'Payment' }} />
          <Stack.Screen name="review/[appointmentId]" options={{ headerShown: true, title: 'Leave Review' }} />
          <Stack.Screen name="review-client/[appointmentId]" options={{ headerShown: true, title: 'Review Client' }} />
          <Stack.Screen name="cancellation-policy" options={{ headerShown: true, title: 'Cancellation Policy' }} />
          <Stack.Screen name="map" options={{ headerShown: true, title: 'Map' }} />
          <Stack.Screen name="provider-services" options={{ headerShown: true, title: 'My Services' }} />
          <Stack.Screen name="portfolio" options={{ headerShown: true, title: 'Portfolio' }} />
          <Stack.Screen name="finances" options={{ headerShown: true, title: 'Finances' }} />
          <Stack.Screen name="feedback" options={{ headerShown: true, title: 'Feedback' }} />
          <Stack.Screen name="documents" options={{ headerShown: true, title: 'Documents' }} />
          <Stack.Screen name="service-history" options={{ headerShown: true, title: 'Service History' }} />
        </Stack>
        <StatusBar style="auto" />
      </ThemeProvider>
      </I18nProvider>
    </AuthProvider>
  );
}
