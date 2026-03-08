import React, { useState, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { Card } from '@/components/ui/Card';
import { Avatar } from '@/components/ui/Avatar';
import { Badge } from '@/components/ui/Badge';
import { StarRating } from '@/components/ui/StarRating';
import { SearchBar } from '@/components/ui/SearchBar';
import { EmptyState } from '@/components/ui/EmptyState';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';
import type { Provider } from '../../src/api/types';

type FilterMode = 'all' | 'online' | 'top_rated';

export default function ProviderSearchScreen() {
  const router = useRouter();
  const { t } = useI18n();

  const FILTERS: { key: FilterMode; label: string }[] = [
    { key: 'all', label: t('all') },
    { key: 'online', label: t('online') },
    { key: 'top_rated', label: t('topRated') },
  ];
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [error, setError] = useState<string | null>(null);

  const fetchProviders = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get('/client/get_providers_list');
      if (res.data?.success) {
        setProviders(res.data.providers || []);
      } else if (Array.isArray(res.data)) {
        setProviders(res.data);
      }
    } catch (err: any) {
      console.error('Failed to fetch providers:', err);
      setError(err.response?.data?.error || err.message || 'Failed to load providers');
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await fetchProviders();
    setLoading(false);
  }, [fetchProviders]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchProviders();
    setRefreshing(false);
  }, [fetchProviders]);

  const filteredProviders = useMemo(() => {
    let result = [...providers];

    // Search text filter
    if (searchText.trim()) {
      const query = searchText.toLowerCase();
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(query) ||
          p.service_names.some((s) => s.toLowerCase().includes(query))
      );
    }

    // Filter mode
    if (filter === 'online') {
      result = result.filter((p) => p.online);
    } else if (filter === 'top_rated') {
      result.sort((a, b) => (b.avg_rating || 0) - (a.avg_rating || 0));
    }

    return result;
  }, [providers, searchText, filter]);

  const renderProvider = ({ item }: { item: Provider }) => {
    const photoUri = item.photo
      ? `https://human-me.com/static/uploads/${item.photo}`
      : null;

    return (
      <Card
        style={styles.providerCard}
        onPress={() => router.push(`/provider/${item.id}` as any)}
      >
        <View style={styles.providerRow}>
          <Avatar uri={photoUri} name={item.name} size={56} online={item.online} />
          <View style={styles.providerInfo}>
            <Text style={styles.providerName}>{item.name}</Text>
            <View style={styles.ratingRow}>
              <StarRating rating={item.avg_rating || 0} size={14} />
              <Text style={styles.reviewCount}>({item.review_count})</Text>
            </View>
            {item.distance_km != null && (
              <Text style={styles.distance}>{item.distance_km.toFixed(1)} km away</Text>
            )}
            {item.service_names.length > 0 && (
              <View style={styles.tagsRow}>
                {item.service_names.slice(0, 3).map((tag, idx) => (
                  <Badge key={idx} label={tag} variant="muted" />
                ))}
                {item.service_names.length > 3 && (
                  <Text style={styles.moreTag}>+{item.service_names.length - 3}</Text>
                )}
              </View>
            )}
          </View>
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

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.headerSection}>
        <View style={styles.titleRow}>
          <Text style={styles.title}>{t('findProvider')}</Text>
          <TouchableOpacity
            style={styles.mapBtn}
            onPress={() => router.push('/map' as any)}
            activeOpacity={0.7}
          >
            <Text style={styles.mapBtnText}>{'\u{1F5FA}'} {t('map')}</Text>
          </TouchableOpacity>
        </View>
        <SearchBar
          value={searchText}
          onChangeText={setSearchText}
          placeholder={t('searchProviders')}
        />
        {/* Filter chips */}
        <View style={styles.filterRow}>
          {FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, filter === f.key && styles.filterChipActive]}
              onPress={() => setFilter(f.key)}
              activeOpacity={0.7}
            >
              <Text
                style={[styles.filterChipText, filter === f.key && styles.filterChipTextActive]}
              >
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {error ? (
        <View style={{ padding: 20, alignItems: 'center' }}>
          <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12 }}>{error}</Text>
          <TouchableOpacity onPress={loadData} style={{ backgroundColor: '#3f4a36', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 }}>
            <Text style={{ color: '#fff', fontWeight: '600' }}>{t('retry') || 'Retry'}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={filteredProviders}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderProvider}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />
          }
          ListEmptyComponent={
            <EmptyState
              icon="person-search"
              title={t('noProviders')}
              subtitle={t('adjustSearchOrFilters') || 'Try adjusting your search or filters'}
            />
          }
        />
      )}
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
  headerSection: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
    gap: 12,
  },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
  },
  mapBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#3f4a36',
  },
  mapBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  filterRow: {
    flexDirection: 'row',
    gap: 8,
  },
  filterChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d1d5db',
  },
  filterChipActive: {
    backgroundColor: '#3f4a36',
    borderColor: '#3f4a36',
  },
  filterChipText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#6b7280',
  },
  filterChipTextActive: {
    color: '#fff',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  providerCard: {
    marginBottom: 12,
  },
  providerRow: {
    flexDirection: 'row',
    gap: 14,
  },
  providerInfo: {
    flex: 1,
    gap: 4,
  },
  providerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  reviewCount: {
    fontSize: 13,
    color: '#6b7280',
  },
  distance: {
    fontSize: 13,
    color: '#6b7280',
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    marginTop: 4,
  },
  moreTag: {
    fontSize: 12,
    color: '#6b7280',
    alignSelf: 'center',
    marginLeft: 2,
  },
});
