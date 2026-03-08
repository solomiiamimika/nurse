import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  Switch,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
  Modal,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import api from '../../src/api/api';
import type { AppointmentEvent } from '../../src/api/types';

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'muted';

function getStatusBadge(status: string): { label: string; variant: BadgeVariant } {
  switch (status) {
    case 'scheduled':
      return { label: 'Pending', variant: 'warning' };
    case 'confirmed':
      return { label: 'Confirmed', variant: 'info' };
    case 'confirmed_paid':
      return { label: 'Paid', variant: 'success' };
    case 'in_progress':
      return { label: 'In Progress', variant: 'success' };
    case 'work_submitted':
      return { label: 'Submitted', variant: 'info' };
    case 'completed':
      return { label: 'Completed', variant: 'success' };
    case 'cancelled':
      return { label: 'Cancelled', variant: 'error' };
    case 'no_show':
      return { label: 'No Show', variant: 'muted' };
    case 'disputed':
      return { label: 'Disputed', variant: 'warning' };
    default:
      return { label: status, variant: 'muted' };
  }
}

export default function ProviderDashboardScreen() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [isOnline, setIsOnline] = useState(false);
  const [appointments, setAppointments] = useState<AppointmentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [togglingOnline, setTogglingOnline] = useState(false);
  const [lateModalVisible, setLateModalVisible] = useState(false);
  const [lateAppointmentId, setLateAppointmentId] = useState<number | null>(null);
  const [lateMinutes, setLateMinutes] = useState('');

  const stats = {
    upcoming: appointments.filter(a => ['scheduled', 'confirmed', 'confirmed_paid'].includes(a.extendedProps?.status)).length,
    completed: appointments.filter(a => a.extendedProps?.status === 'completed').length,
    pending: appointments.filter(a => a.extendedProps?.status === 'scheduled').length,
  };

  const fetchAppointments = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get('/provider/get_appointments');
      const raw = res.data;
      const list = Array.isArray(raw) ? raw : (raw?.data ?? raw?.appointments ?? []);
      // Normalize flat items into AppointmentEvent-like shape
      const normalized = list.map((item: any) => {
        if (item.extendedProps) return item;
        return {
          ...item,
          start: item.start || item.appointment_start_time,
          end: item.end || item.appointment_start_time,
          extendedProps: {
            status: item.status || 'scheduled',
            client_name: item.patient_name || item.client_name || '',
            service_name: item.service_name || 'Service',
            appointment_id: item.id,
            amount: item.payment ? String(item.payment) : '0',
            notes: item.notes || '',
          },
        };
      });
      setAppointments(normalized);
    } catch (err: any) {
      console.error('Failed to fetch appointments:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load appointments');
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await fetchAppointments();
    setLoading(false);
  }, [fetchAppointments]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchAppointments();
    setRefreshing(false);
  }, [fetchAppointments]);

  const toggleOnline = async (value: boolean) => {
    setTogglingOnline(true);
    try {
      await api.post('/provider/toggle_online', { online: value });
      setIsOnline(value);
    } catch (err) {
      Alert.alert(t('error'), t('failedUpdateOnline'));
    } finally {
      setTogglingOnline(false);
    }
  };

  const handleAction = async (appointmentId: number, newStatus: string) => {
    try {
      await api.post('/provider/update_appointment_status', {
        appointment_id: appointmentId,
        status: newStatus,
      });
      Alert.alert(t('success'), newStatus === 'confirmed' ? t('appointmentAccepted') : t('appointmentMarkedDone'));
      await fetchAppointments();
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to update appointment';
      Alert.alert(t('error'), msg);
    }
  };

  const handleConfirmArrival = async (appointmentId: number) => {
    try {
      await api.post('/provider/confirm_arrival', { appointment_id: appointmentId });
      Alert.alert(t('success'), t('arrivalConfirmed') || 'Arrival confirmed');
      await fetchAppointments();
    } catch (err: any) {
      Alert.alert(t('error'), err.response?.data?.message || 'Failed');
    }
  };

  const handleReportLate = async () => {
    if (!lateAppointmentId || !lateMinutes.trim()) return;
    try {
      await api.post('/provider/report_late', {
        appointment_id: lateAppointmentId,
        delay_minutes: parseInt(lateMinutes),
      });
      Alert.alert(t('success'), t('lateReported') || 'Late notification sent');
      setLateModalVisible(false);
      setLateAppointmentId(null);
      setLateMinutes('');
    } catch (err: any) {
      Alert.alert(t('error'), err.response?.data?.message || 'Failed');
    }
  };

  const handleReportNoShow = (appointmentId: number) => {
    Alert.alert(
      t('reportNoShow') || 'Report No-Show',
      t('confirmNoShow') || 'Confirm that the client did not show up?',
      [
        { text: t('cancel'), style: 'cancel' },
        {
          text: t('confirm'),
          style: 'destructive',
          onPress: async () => {
            try {
              await api.post('/provider/report_no_show', { appointment_id: appointmentId });
              Alert.alert(t('success'), t('noShowRecorded') || 'No-show recorded');
              await fetchAppointments();
            } catch (err: any) {
              Alert.alert(t('error'), err.response?.data?.message || 'Failed');
            }
          },
        },
      ]
    );
  };

  const isNoShowEligible = (item: AppointmentEvent) => {
    const apptTime = new Date(item.start);
    const now = new Date();
    return now.getTime() > apptTime.getTime() + 15 * 60 * 1000;
  };

  const renderAppointment = ({ item }: { item: AppointmentEvent }) => {
    const { status, client_name, service_name } = item.extendedProps;
    const appointmentId = item.id;
    const badge = getStatusBadge(status);
    const startDate = new Date(item.start);

    return (
      <Card style={styles.appointmentCard}>
        <View style={styles.appointmentHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.clientName}>{client_name || t('client')}</Text>
            <Text style={styles.serviceName}>{service_name}</Text>
          </View>
          <Badge label={badge.label} variant={badge.variant} />
        </View>

        <View style={styles.dateRow}>
          <Text style={styles.dateText}>
            {startDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          </Text>
          <Text style={styles.timeText}>
            {startDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
          </Text>
        </View>

        <View style={styles.actionRow}>
          {status === 'scheduled' && (
            <TouchableOpacity
              style={styles.acceptBtn}
              onPress={() => handleAction(appointmentId, 'confirmed')}
            >
              <Text style={styles.acceptBtnText}>{t('accept')}</Text>
            </TouchableOpacity>
          )}
          {(status === 'confirmed_paid') && (
            <>
              <TouchableOpacity
                style={styles.arrivalBtn}
                onPress={() => handleConfirmArrival(appointmentId)}
              >
                <Text style={styles.arrivalBtnText}>{t('confirmArrival') || 'Confirm Arrival'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.lateBtn}
                onPress={() => {
                  setLateAppointmentId(appointmentId);
                  setLateMinutes('');
                  setLateModalVisible(true);
                }}
              >
                <Text style={styles.lateBtnText}>{t('runningLate') || 'Running Late'}</Text>
              </TouchableOpacity>
              {isNoShowEligible(item) && (
                <TouchableOpacity
                  style={styles.noShowBtn}
                  onPress={() => handleReportNoShow(appointmentId)}
                >
                  <Text style={styles.noShowBtnText}>{t('clientNoShow') || 'Client No-Show'}</Text>
                </TouchableOpacity>
              )}
            </>
          )}
          {status === 'in_progress' && (
            <TouchableOpacity
              style={styles.doneBtn}
              onPress={() => handleAction(appointmentId, 'work_submitted')}
            >
              <Text style={styles.doneBtnText}>{t('markDone')}</Text>
            </TouchableOpacity>
          )}
          {(status === 'confirmed') && (
            <TouchableOpacity
              style={styles.doneBtn}
              onPress={() => handleAction(appointmentId, 'work_submitted')}
            >
              <Text style={styles.doneBtnText}>{t('markDone')}</Text>
            </TouchableOpacity>
          )}
          {status === 'completed' && (
            <TouchableOpacity
              style={styles.reviewBtn}
              onPress={() => router.push(`/review-client/${appointmentId}` as any)}
            >
              <Text style={styles.reviewBtnText}>{t('reviewClient')}</Text>
            </TouchableOpacity>
          )}
        </View>
      </Card>
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={styles.centered}>
        <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12, textAlign: 'center', paddingHorizontal: 20 }}>{error}</Text>
        <TouchableOpacity style={{ backgroundColor: '#3f4a36', paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8 }} onPress={loadData}>
          <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>{t('retry') || 'Retry'}</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.greeting}>{t('hello')}, {user?.full_name || user?.username || t('provider')}</Text>
        <View style={styles.onlineRow}>
          <Text style={styles.onlineLabel}>{isOnline ? t('onlineStatus') : t('offlineStatus')}</Text>
          <Switch
            value={isOnline}
            onValueChange={toggleOnline}
            trackColor={{ false: '#d1d5db', true: '#86efac' }}
            thumbColor={isOnline ? '#22c55e' : '#9ca3af'}
            disabled={togglingOnline}
          />
        </View>
      </View>

      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statNumber}>{stats.upcoming}</Text>
          <Text style={styles.statLabel}>{t('upcoming')}</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statNumber}>{stats.pending}</Text>
          <Text style={styles.statLabel}>{t('pending')}</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statNumber}>{stats.completed}</Text>
          <Text style={styles.statLabel}>{t('completed')}</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>{t('appointments')}</Text>

      <FlatList
        data={appointments.filter(a =>
          ['scheduled', 'confirmed', 'confirmed_paid', 'in_progress', 'work_submitted', 'completed', 'no_show', 'disputed'].includes(a.extendedProps?.status)
        )}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderAppointment}
        contentContainerStyle={styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />}
        ListEmptyComponent={
          <EmptyState
            icon="event"
            title={t('noUpcomingAppointments')}
            subtitle={t('scheduleIsClear')}
          />
        }
      />

      {/* Running Late Modal */}
      <Modal
        visible={lateModalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setLateModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>{t('runningLate') || 'Running Late'}</Text>
            <Text style={styles.modalSubtitle}>{t('howManyMinutes') || 'How many minutes late?'}</Text>
            <TextInput
              style={styles.lateInput}
              placeholder="15"
              keyboardType="numeric"
              value={lateMinutes}
              onChangeText={setLateMinutes}
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setLateModalVisible(false)}>
                <Text style={styles.modalCancelText}>{t('cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalConfirmBtn} onPress={handleReportLate}>
                <Text style={styles.modalConfirmText}>{t('confirm')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  greeting: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
  },
  onlineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  onlineLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    gap: 12,
    marginBottom: 16,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  statNumber: {
    fontSize: 24,
    fontWeight: '700',
    color: '#3f4a36',
  },
  statLabel: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    paddingHorizontal: 20,
    marginBottom: 8,
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  appointmentCard: {
    marginBottom: 12,
  },
  appointmentHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  clientName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  serviceName: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 2,
  },
  dateRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 10,
  },
  dateText: {
    fontSize: 14,
    color: '#374151',
    fontWeight: '500',
  },
  timeText: {
    fontSize: 14,
    color: '#6b7280',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  acceptBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
  },
  acceptBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  doneBtn: {
    backgroundColor: '#2563eb',
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
  },
  doneBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  reviewBtn: {
    backgroundColor: '#f0f1ee',
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
  },
  reviewBtnText: {
    color: '#3f4a36',
    fontSize: 14,
    fontWeight: '600',
  },
  arrivalBtn: {
    backgroundColor: '#10b981',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  arrivalBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  lateBtn: {
    backgroundColor: '#f59e0b',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  lateBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  noShowBtn: {
    backgroundColor: '#6b7280',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  noShowBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    paddingHorizontal: 30,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 8,
  },
  modalSubtitle: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 16,
  },
  lateInput: {
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    marginBottom: 16,
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#f3f4f6',
    alignItems: 'center',
  },
  modalCancelText: {
    color: '#374151',
    fontWeight: '600',
  },
  modalConfirmBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#f59e0b',
    alignItems: 'center',
  },
  modalConfirmText: {
    color: '#fff',
    fontWeight: '600',
  },
});
