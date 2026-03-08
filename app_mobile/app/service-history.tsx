import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import { Card } from '@/components/ui/Card';
import api from '../src/api/api';

interface HistoryItem {
  id: number;
  service_name: string;
  provider_name?: string;
  client_name?: string;
  date: string;
  amount: number | string;
  status: string;
}

export default function ServiceHistoryScreen() {
  const { user } = useAuth();
  const { t } = useI18n();

  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const isProvider = user?.role === 'provider';

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const endpoint = isProvider
        ? '/provider/service_history'
        : '/client/client_get_history';
      const res = await api.get(endpoint);
      const data = res.data;
      setItems(Array.isArray(data) ? data : data?.history || data?.items || []);
    } catch (err) {
      console.error('Failed to fetch service history:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'completed':
      case 'done':
        return '#16a34a';
      case 'cancelled':
        return '#ef4444';
      case 'pending':
        return '#f59e0b';
      default:
        return '#6b7280';
    }
  };

  const renderItem = useCallback(({ item }: { item: HistoryItem }) => {
    const counterpartName = isProvider ? item.client_name : item.provider_name;
    const amount = typeof item.amount === 'number'
      ? `$${item.amount.toFixed(2)}`
      : item.amount
        ? `$${parseFloat(String(item.amount)).toFixed(2)}`
        : '--';

    return (
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.serviceName} numberOfLines={1}>{item.service_name || 'Service'}</Text>
          <Text style={[styles.status, { color: getStatusColor(item.status) }]}>
            {item.status}
          </Text>
        </View>
        {counterpartName ? (
          <Text style={styles.counterpart} numberOfLines={1}>
            {isProvider ? 'Client' : 'Provider'}: {counterpartName}
          </Text>
        ) : null}
        <View style={styles.cardFooter}>
          <Text style={styles.date}>{formatDate(item.date)}</Text>
          <Text style={styles.amount}>{amount}</Text>
        </View>
      </Card>
    );
  }, [isProvider]);

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: t('serviceHistory') }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ headerShown: true, title: t('serviceHistory') }} />
      <FlatList
        data={items}
        keyExtractor={item => String(item.id)}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>{t('noHistory')}</Text>
          </View>
        }
      />
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
  listContent: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 10,
  },
  card: {
    paddingVertical: 14,
    paddingHorizontal: 16,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  serviceName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    flex: 1,
    marginRight: 8,
  },
  status: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  counterpart: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 8,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  date: {
    fontSize: 13,
    color: '#9ca3af',
  },
  amount: {
    fontSize: 16,
    fontWeight: '700',
    color: '#3f4a36',
  },
  empty: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#9ca3af',
  },
});
