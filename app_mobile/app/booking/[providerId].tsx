import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Card } from '@/components/ui/Card';
import api from '../../src/api/api';
import type { ProviderService } from '../../src/api/types';

function getNext14Days(): { date: string; label: string; dayName: string }[] {
  const days: { date: string; label: string; dayName: string }[] = [];
  const now = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(now);
    d.setDate(now.getDate() + i);
    days.push({
      date: d.toISOString().split('T')[0],
      label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      dayName: d.toLocaleDateString('en-US', { weekday: 'short' }),
    });
  }
  return days;
}

export default function BookingScreen() {
  const { providerId } = useLocalSearchParams<{ providerId: string }>();
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [services, setServices] = useState<ProviderService[]>([]);
  const [loadingServices, setLoadingServices] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Select service
  const [selectedService, setSelectedService] = useState<ProviderService | null>(null);

  // Step 2: Select date
  const days = getNext14Days();
  const [selectedDate, setSelectedDate] = useState<string>('');

  // Step 3: Select time
  const [availableTimes, setAvailableTimes] = useState<string[]>([]);
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [loadingTimes, setLoadingTimes] = useState(false);

  // Step 4: Confirm
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchServices();
  }, [providerId]);

  useEffect(() => {
    if (selectedService && selectedDate) {
      fetchAvailableTimes();
    }
  }, [selectedDate, selectedService]);

  const fetchServices = async () => {
    setLoadingServices(true);
    setError(null);
    try {
      const res = await api.get(`/client/get_provider_services?provider_id=${providerId}`);
      const raw = res.data;
      const data = Array.isArray(raw) ? raw : Array.isArray(raw?.services) ? raw.services : Array.isArray(raw?.data) ? raw.data : [];
      setServices(data);
    } catch (err: any) {
      console.error('Failed to fetch services:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load services');
    } finally {
      setLoadingServices(false);
    }
  };

  const fetchAvailableTimes = async () => {
    if (!selectedService || !selectedDate) return;
    setLoadingTimes(true);
    setSelectedTime('');
    try {
      const res = await api.get(
        `/client/get_available_times?provider_id=${providerId}&service_id=${selectedService.id}&date=${selectedDate}`
      );
      const raw = res.data;
      const times = Array.isArray(raw) ? raw : Array.isArray(raw?.data) ? raw.data : Array.isArray(raw?.times) ? raw.times : [];
      setAvailableTimes(times);
    } catch (err: any) {
      console.error('Failed to fetch times:', err);
      setAvailableTimes([]);
    } finally {
      setLoadingTimes(false);
    }
  };

  const handleConfirm = async () => {
    if (!selectedService || !selectedDate || !selectedTime) return;

    setSubmitting(true);
    try {
      const dateTime = `${selectedDate} ${selectedTime}`;
      await api.post('/client/create_appointment', {
        provider_id: parseInt(providerId, 10),
        service_id: selectedService.id,
        date_time: dateTime,
        notes,
      });
      Alert.alert('Booking Confirmed', 'Your appointment has been booked successfully!', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to create appointment';
      Alert.alert('Error', msg);
    } finally {
      setSubmitting(false);
    }
  };

  const canGoNext = () => {
    switch (step) {
      case 1:
        return selectedService !== null;
      case 2:
        return selectedDate !== '';
      case 3:
        return selectedTime !== '';
      default:
        return true;
    }
  };

  const renderStepIndicator = () => (
    <View style={styles.stepIndicator}>
      {[1, 2, 3, 4].map(s => (
        <View key={s} style={styles.stepRow}>
          <View style={[styles.stepDot, s <= step && styles.stepDotActive]}>
            <Text style={[styles.stepDotText, s <= step && styles.stepDotTextActive]}>{s}</Text>
          </View>
          {s < 4 && <View style={[styles.stepLine, s < step && styles.stepLineActive]} />}
        </View>
      ))}
    </View>
  );

  // Step 1: Select Service
  const renderStep1 = () => (
    <View style={styles.stepContent}>
      <Text style={styles.stepTitle}>Select a Service</Text>
      {loadingServices ? (
        <ActivityIndicator size="large" color="#3f4a36" style={{ marginTop: 40 }} />
      ) : error ? (
        <View style={{ alignItems: 'center', paddingVertical: 40 }}>
          <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12, textAlign: 'center' }}>{error}</Text>
          <TouchableOpacity style={{ backgroundColor: '#3f4a36', paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8 }} onPress={fetchServices}>
            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : services.length === 0 ? (
        <Text style={styles.emptyText}>No services available</Text>
      ) : (
        services.map(service => (
          <Card
            key={service.id}
            style={[
              styles.serviceOption,
              selectedService?.id === service.id && styles.serviceOptionSelected,
            ]}
            onPress={() => setSelectedService(service)}
          >
            <Text style={styles.serviceOptionName}>{service.name}</Text>
            <View style={styles.serviceOptionMeta}>
              <Text style={styles.serviceOptionPrice}>${service.price}</Text>
              <Text style={styles.serviceOptionDuration}>{service.duration} min</Text>
            </View>
            {service.description && (
              <Text style={styles.serviceOptionDesc} numberOfLines={2}>
                {service.description}
              </Text>
            )}
          </Card>
        ))
      )}
    </View>
  );

  // Step 2: Select Date
  const renderStep2 = () => (
    <View style={styles.stepContent}>
      <Text style={styles.stepTitle}>Select a Date</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.dateScroll}>
        {days.map(day => (
          <TouchableOpacity
            key={day.date}
            style={[styles.dayBtn, selectedDate === day.date && styles.dayBtnActive]}
            onPress={() => setSelectedDate(day.date)}
          >
            <Text style={[styles.dayName, selectedDate === day.date && styles.dayTextActive]}>
              {day.dayName}
            </Text>
            <Text style={[styles.dayLabel, selectedDate === day.date && styles.dayTextActive]}>
              {day.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );

  // Step 3: Select Time
  const renderStep3 = () => (
    <View style={styles.stepContent}>
      <Text style={styles.stepTitle}>Select a Time</Text>
      {loadingTimes ? (
        <ActivityIndicator size="large" color="#3f4a36" style={{ marginTop: 40 }} />
      ) : availableTimes.length === 0 ? (
        <Text style={styles.emptyText}>No available times for this date</Text>
      ) : (
        <View style={styles.timeGrid}>
          {availableTimes.map(time => (
            <TouchableOpacity
              key={time}
              style={[styles.timeChip, selectedTime === time && styles.timeChipActive]}
              onPress={() => setSelectedTime(time)}
            >
              <Text style={[styles.timeChipText, selectedTime === time && styles.timeChipTextActive]}>
                {time}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );

  // Step 4: Confirm
  const renderStep4 = () => (
    <View style={styles.stepContent}>
      <Text style={styles.stepTitle}>Confirm Booking</Text>
      <Card style={styles.summaryCard}>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Service</Text>
          <Text style={styles.summaryValue}>{selectedService?.name}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Date</Text>
          <Text style={styles.summaryValue}>{selectedDate}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Time</Text>
          <Text style={styles.summaryValue}>{selectedTime}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Price</Text>
          <Text style={styles.summaryValue}>${selectedService?.price}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Duration</Text>
          <Text style={styles.summaryValue}>{selectedService?.duration} min</Text>
        </View>
      </Card>

      <Text style={styles.notesLabel}>Notes (optional)</Text>
      <TextInput
        style={styles.notesInput}
        value={notes}
        onChangeText={setNotes}
        placeholder="Any special instructions..."
        multiline
        numberOfLines={3}
        textAlignVertical="top"
      />
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ title: 'Book Appointment' }} />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {renderStepIndicator()}

        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
        {step === 4 && renderStep4()}
      </ScrollView>

      <View style={styles.bottomBar}>
        {step > 1 && (
          <TouchableOpacity style={styles.backBtn} onPress={() => setStep(step - 1)}>
            <Text style={styles.backBtnText}>Back</Text>
          </TouchableOpacity>
        )}
        <View style={{ flex: 1 }} />
        {step < 4 ? (
          <TouchableOpacity
            style={[styles.nextBtn, !canGoNext() && styles.nextBtnDisabled]}
            onPress={() => canGoNext() && setStep(step + 1)}
            disabled={!canGoNext()}
          >
            <Text style={styles.nextBtnText}>Next</Text>
          </TouchableOpacity>
        ) : submitting ? (
          <ActivityIndicator size="small" color="#3f4a36" />
        ) : (
          <TouchableOpacity style={styles.confirmBtn} onPress={handleConfirm}>
            <Text style={styles.confirmBtnText}>Confirm Booking</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 20,
  },
  stepIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  stepDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#e5e7eb',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepDotActive: {
    backgroundColor: '#3f4a36',
  },
  stepDotText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#9ca3af',
  },
  stepDotTextActive: {
    color: '#fff',
  },
  stepLine: {
    width: 40,
    height: 2,
    backgroundColor: '#e5e7eb',
  },
  stepLineActive: {
    backgroundColor: '#3f4a36',
  },
  stepContent: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
    paddingVertical: 40,
  },
  // Step 1 - Service selection
  serviceOption: {
    marginBottom: 10,
  },
  serviceOptionSelected: {
    borderColor: '#3f4a36',
    borderWidth: 2,
  },
  serviceOptionName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  serviceOptionMeta: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 4,
  },
  serviceOptionPrice: {
    fontSize: 16,
    fontWeight: '700',
    color: '#3f4a36',
  },
  serviceOptionDuration: {
    fontSize: 14,
    color: '#6b7280',
  },
  serviceOptionDesc: {
    fontSize: 13,
    color: '#9ca3af',
  },
  // Step 2 - Date selection
  dateScroll: {
    marginBottom: 16,
  },
  dayBtn: {
    width: 70,
    paddingVertical: 14,
    marginRight: 8,
    borderRadius: 10,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    alignItems: 'center',
  },
  dayBtnActive: {
    backgroundColor: '#3f4a36',
    borderColor: '#3f4a36',
  },
  dayName: {
    fontSize: 12,
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: 4,
  },
  dayLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1f2937',
  },
  dayTextActive: {
    color: '#fff',
  },
  // Step 3 - Time selection
  timeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  timeChip: {
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  timeChipActive: {
    backgroundColor: '#3f4a36',
    borderColor: '#3f4a36',
  },
  timeChipText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  timeChipTextActive: {
    color: '#fff',
  },
  // Step 4 - Summary
  summaryCard: {
    marginBottom: 16,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  summaryLabel: {
    fontSize: 14,
    color: '#6b7280',
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
  },
  notesLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  notesInput: {
    height: 80,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 15,
    paddingTop: 12,
    backgroundColor: '#fff',
    fontSize: 16,
  },
  // Bottom bar
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    backgroundColor: '#fff',
  },
  backBtn: {
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d1d5db',
  },
  backBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#374151',
  },
  nextBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: 8,
  },
  nextBtnDisabled: {
    backgroundColor: '#9ca3af',
  },
  nextBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  confirmBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
  },
  confirmBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
