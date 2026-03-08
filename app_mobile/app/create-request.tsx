import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import api from '../src/api/api';

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

function generateTimeSlots(): string[] {
  const slots: string[] = [];
  for (let h = 8; h <= 20; h++) {
    slots.push(`${h.toString().padStart(2, '0')}:00`);
    if (h < 20) {
      slots.push(`${h.toString().padStart(2, '0')}:30`);
    }
  }
  return slots;
}

export default function CreateRequestScreen() {
  const router = useRouter();

  const [serviceName, setServiceName] = useState('');
  const [description, setDescription] = useState('');
  const [address, setAddress] = useState('');
  const [district, setDistrict] = useState('');
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedTime, setSelectedTime] = useState('');
  const [budget, setBudget] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);

  const days = getNext14Days();
  const timeSlots = generateTimeSlots();

  const handleSubmit = async () => {
    if (!serviceName.trim()) {
      Alert.alert('Error', 'Service name is required');
      return;
    }

    setSubmitting(true);
    try {
      const dateTime = selectedDate && selectedTime ? `${selectedDate} ${selectedTime}` : undefined;

      await api.post('/client/client_self_create_appointment', {
        service_name: serviceName.trim(),
        description: description.trim(),
        address: address.trim(),
        district: district.trim(),
        appointment_start_time: dateTime,
        payment: budget ? parseFloat(budget) : undefined,
        notes: notes.trim(),
      });

      Alert.alert('Success', 'Your request has been submitted!', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to create request';
      Alert.alert('Error', msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ title: 'New Request', presentation: 'modal' }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <Text style={styles.label}>
            Service Name <Text style={styles.required}>*</Text>
          </Text>
          <TextInput
            style={styles.input}
            value={serviceName}
            onChangeText={setServiceName}
            placeholder="e.g., Home Cleaning, Massage, etc."
          />

          <Text style={styles.label}>Description</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={description}
            onChangeText={setDescription}
            placeholder="Describe what you need..."
            multiline
            numberOfLines={3}
            textAlignVertical="top"
          />

          <Text style={styles.label}>Address</Text>
          <TextInput
            style={styles.input}
            value={address}
            onChangeText={setAddress}
            placeholder="Enter address"
          />

          <Text style={styles.label}>District</Text>
          <TextInput
            style={styles.input}
            value={district}
            onChangeText={setDistrict}
            placeholder="Enter district"
          />

          <Text style={styles.label}>Preferred Date</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.dateScroll}>
            {days.map(day => (
              <TouchableOpacity
                key={day.date}
                style={[styles.dayBtn, selectedDate === day.date && styles.dayBtnActive]}
                onPress={() => {
                  setSelectedDate(day.date);
                  setShowTimePicker(true);
                }}
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

          {showTimePicker && selectedDate !== '' && (
            <>
              <Text style={styles.label}>Preferred Time</Text>
              <View style={styles.timeGrid}>
                {timeSlots.map(time => (
                  <TouchableOpacity
                    key={time}
                    style={[styles.timeChip, selectedTime === time && styles.timeChipActive]}
                    onPress={() => setSelectedTime(time)}
                  >
                    <Text
                      style={[styles.timeChipText, selectedTime === time && styles.timeChipTextActive]}
                    >
                      {time}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </>
          )}

          <Text style={styles.label}>Budget ($)</Text>
          <TextInput
            style={styles.input}
            value={budget}
            onChangeText={setBudget}
            placeholder="Enter your budget"
            keyboardType="numeric"
          />

          <Text style={styles.label}>Notes</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={notes}
            onChangeText={setNotes}
            placeholder="Any additional notes..."
            multiline
            numberOfLines={3}
            textAlignVertical="top"
          />

          {submitting ? (
            <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 24 }} />
          ) : (
            <TouchableOpacity style={styles.submitBtn} onPress={handleSubmit}>
              <Text style={styles.submitBtnText}>Submit</Text>
            </TouchableOpacity>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
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
    paddingBottom: 40,
  },
  label: {
    marginBottom: 8,
    color: '#333',
    fontWeight: '600',
    fontSize: 14,
    marginTop: 8,
  },
  required: {
    color: '#ef4444',
  },
  input: {
    height: 50,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 12,
    paddingHorizontal: 15,
    borderRadius: 10,
    backgroundColor: '#fff',
    fontSize: 16,
  },
  textArea: {
    height: 90,
    paddingTop: 12,
  },
  dateScroll: {
    marginBottom: 12,
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
  timeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 12,
  },
  timeChip: {
    paddingVertical: 8,
    paddingHorizontal: 16,
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
  submitBtn: {
    backgroundColor: '#3f4a36',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});
