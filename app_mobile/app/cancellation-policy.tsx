import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useI18n } from '@/contexts/I18nContext';
import api from '../src/api/api';

export default function CancellationPolicyScreen() {
  const { t } = useI18n();

  const [freeCancelHours, setFreeCancelHours] = useState('24');
  const [lateCancelFeePercent, setLateCancelFeePercent] = useState('50');
  const [noShowFeePercent, setNoShowFeePercent] = useState('100');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadPolicy();
  }, []);

  const loadPolicy = async () => {
    setLoading(true);
    try {
      const res = await api.get('/provider/cancellation_policy');
      const data = res.data;
      setFreeCancelHours(String(data.free_cancel_hours ?? 24));
      setLateCancelFeePercent(String(data.late_cancel_fee_percent ?? 50));
      setNoShowFeePercent(String(data.no_show_fee_percent ?? 100));
    } catch (err) {
      // Use defaults on error
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    const hours = parseInt(freeCancelHours, 10);
    const lateFee = parseInt(lateCancelFeePercent, 10);
    const noShowFee = parseInt(noShowFeePercent, 10);

    if (isNaN(hours) || isNaN(lateFee) || isNaN(noShowFee)) {
      Alert.alert(t('error'), 'Please enter valid numbers');
      return;
    }

    setSaving(true);
    try {
      await api.post('/provider/cancellation_policy', {
        free_cancel_hours: hours,
        late_cancel_fee_percent: lateFee,
        no_show_fee_percent: noShowFee,
      });
      Alert.alert(t('success'), t('policyUpdated'));
    } catch (err: any) {
      const msg = err.response?.data?.msg || t('error');
      Alert.alert(t('error'), msg);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: t('setCancellationPolicy') }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: true, title: t('setCancellationPolicy') }} />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.content}>
          {/* Free Cancellation Hours */}
          <Text style={styles.label}>{t('freeCancelHours')}</Text>
          <TextInput
            style={styles.input}
            value={freeCancelHours}
            onChangeText={setFreeCancelHours}
            keyboardType="numeric"
            placeholder="24"
          />
          <Text style={styles.explanation}>
            Clients can cancel for free up to this many hours before the appointment.
          </Text>

          {/* Late Cancellation Fee */}
          <Text style={styles.label}>{t('lateFeePercent')}</Text>
          <TextInput
            style={styles.input}
            value={lateCancelFeePercent}
            onChangeText={setLateCancelFeePercent}
            keyboardType="numeric"
            placeholder="50"
          />
          <Text style={styles.explanation}>
            Percentage of the service price charged when a client cancels after the free cancellation window.
          </Text>

          {/* No-Show Fee */}
          <Text style={styles.label}>{t('noShowFeePercent')}</Text>
          <TextInput
            style={styles.input}
            value={noShowFeePercent}
            onChangeText={setNoShowFeePercent}
            keyboardType="numeric"
            placeholder="100"
          />
          <Text style={styles.explanation}>
            Percentage of the service price charged when a client does not show up for the appointment.
          </Text>

          {/* Save Button */}
          {saving ? (
            <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 20 }} />
          ) : (
            <TouchableOpacity style={styles.saveBtn} onPress={handleSave}>
              <Text style={styles.saveBtnText}>{t('save')}</Text>
            </TouchableOpacity>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 24,
    paddingBottom: 40,
  },
  label: {
    marginBottom: 8,
    color: '#333',
    fontWeight: '600',
    fontSize: 14,
  },
  input: {
    height: 50,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 8,
    paddingHorizontal: 15,
    borderRadius: 10,
    backgroundColor: '#fff',
    fontSize: 16,
  },
  explanation: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 24,
    lineHeight: 18,
  },
  saveBtn: {
    backgroundColor: '#3f4a36',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});
