import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter, Stack } from 'expo-router';

export default function MapScreen() {
  const router = useRouter();

  return (
    <View style={styles.container}>
      <Stack.Screen options={{ headerShown: true, title: 'Map' }} />
      <View style={styles.centered}>
        <Text style={styles.title}>Map is available on mobile only</Text>
        <Text style={styles.subtitle}>Please use the mobile app to view the map.</Text>
        <TouchableOpacity
          style={styles.backBtn}
          onPress={() => router.back()}
          activeOpacity={0.8}
        >
          <Text style={styles.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  title: { fontSize: 18, fontWeight: '600', color: '#374151', marginBottom: 8 },
  subtitle: { fontSize: 14, color: '#9ca3af', marginBottom: 20 },
  backBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 25,
  },
  backBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
});
