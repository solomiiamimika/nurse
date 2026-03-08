import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
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
      return { label: 'Scheduled', variant: 'info' };
    case 'confirmed':
      return { label: 'Confirmed', variant: 'warning' };
    case 'confirmed_paid':
      return { label: 'Paid', variant: 'success' };
    case 'work_submitted':
      return { label: 'Submitted', variant: 'info' };
    case 'completed':
      return { label: 'Completed', variant: 'success' };
    case 'cancelled':
      return { label: 'Cancelled', variant: 'error' };
    default:
      return { label: status, variant: 'muted' };
  }
}

export default function ClientHomeScreen() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [appointments, setAppointments] = useState<AppointmentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUpcoming = useCallback(async () => {
    setError(null);
    try {
      const today = new Date();
      const weekLater = new Date();
      weekLater.setDate(today.getDate() + 7);

      const startStr = today.toISOString().split('T')[0];
      const endStr = weekLater.toISOString().split('T')[0];

      const res = await api.get('/client/get_appointments', {
        params: { start: startStr, end: endStr },
      });
      const raw = res.data;
      const items = Array.isArray(raw) ? raw : (raw?.data ?? raw?.appointments ?? []);
      setAppointments(items);
    } catch (err: any) {
      console.error('Failed to fetch upcoming appointments:', err);
      setError(err.response?.data?.error || err.message || 'Failed to load appointments');
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await fetchUpcoming();
    setLoading(false);
  }, [fetchUpcoming]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchUpcoming();
    setRefreshing(false);
  }, [fetchUpcoming]);

  const upcomingThree = appointments.slice(0, 3);

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />
        }
      >
        {/* Greeting */}
        <Text style={styles.greeting}>{t('hello')}, {user?.full_name || user?.username || 'Client'}!</Text>

        {error && (
          <View style={{ padding: 20, alignItems: 'center' }}>
            <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12 }}>{error}</Text>
            <TouchableOpacity onPress={loadData} style={{ backgroundColor: '#3f4a36', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 }}>
              <Text style={{ color: '#fff', fontWeight: '600' }}>{t('retry') || 'Retry'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <TouchableOpacity
            style={styles.quickActionBtn}
            onPress={() => router.push('/(client-tabs)/search')}
            activeOpacity={0.7}
          >
            <MaterialIcons name="search" size={24} color="#fff" />
            <Text style={styles.quickActionText}>{t('findProvider')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quickActionBtn, styles.quickActionSecondary]}
            onPress={() => router.push('/create-request' as any)}
            activeOpacity={0.7}
          >
            <MaterialIcons name="add-circle-outline" size={24} color="#3f4a36" />
            <Text style={[styles.quickActionText, styles.quickActionTextSecondary]}>
              {t('createRequest')}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Upcoming Appointments */}
        <Text style={styles.sectionTitle}>{t('upcomingAppointments')}</Text>

        {upcomingThree.length === 0 ? (
          <EmptyState
            icon="event"
            title={t('noAppointments')}
            subtitle={t('bookServiceToStart') || 'Book a service to get started'}
          />
        ) : (
          upcomingThree.map((item) => {
            const { status, service_name, provider_name } = item.extendedProps;
            const badge = getStatusBadge(status);
            const startDate = new Date(item.start);

            return (
              <Card key={item.id} style={styles.appointmentCard}>
                <View style={styles.appointmentHeader}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.serviceName}>{service_name}</Text>
                    <Text style={styles.providerName}>{provider_name || 'Provider'}</Text>
                  </View>
                  <Badge label={badge.label} variant={badge.variant} />
                </View>
                <View style={styles.dateRow}>
                  <MaterialIcons name="event" size={16} color="#6b7280" />
                  <Text style={styles.dateText}>
                    {startDate.toLocaleDateString('en-US', {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </Text>
                  <MaterialIcons name="schedule" size={16} color="#6b7280" />
                  <Text style={styles.timeText}>
                    {startDate.toLocaleTimeString('en-US', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
              </Card>
            );
          })
        )}

        {appointments.length > 3 && (
          <TouchableOpacity
            style={styles.viewAllBtn}
            onPress={() => router.push('/(client-tabs)/appointments')}
          >
            <Text style={styles.viewAllText}>{t('viewAll')}</Text>
            <MaterialIcons name="chevron-right" size={20} color="#3f4a36" />
          </TouchableOpacity>
        )}
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
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  greeting: {
    fontSize: 24,
    fontWeight: '700',
    color: '#3f4a36',
    marginTop: 8,
    marginBottom: 20,
  },
  quickActions: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 24,
  },
  quickActionBtn: {
    flex: 1,
    backgroundColor: '#3f4a36',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: 12,
  },
  quickActionSecondary: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#3f4a36',
  },
  quickActionText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  quickActionTextSecondary: {
    color: '#3f4a36',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 12,
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
  serviceName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  providerName: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 2,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dateText: {
    fontSize: 14,
    color: '#374151',
    fontWeight: '500',
    marginRight: 8,
  },
  timeText: {
    fontSize: 14,
    color: '#6b7280',
  },
  viewAllBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    marginTop: 4,
  },
  viewAllText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3f4a36',
  },
});
