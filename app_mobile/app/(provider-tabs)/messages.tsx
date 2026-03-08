import React, { useState, useCallback } from 'react';
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
import { Avatar } from '@/components/ui/Avatar';
import { EmptyState } from '@/components/ui/EmptyState';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';
import type { Conversation } from '../../src/api/types';

export default function ProviderMessagesScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = useCallback(async () => {
    try {
      setError(null);
      const res = await api.get('/api/conversations');
      const raw = res.data;
      const list = Array.isArray(raw) ? raw : Array.isArray(raw?.data) ? raw.data : Array.isArray(raw?.conversations) ? raw.conversations : [];
      setConversations(list);
    } catch (err: any) {
      console.error('Failed to fetch conversations:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load conversations');
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await fetchConversations();
    setLoading(false);
  }, [fetchConversations]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchConversations();
    setRefreshing(false);
  }, [fetchConversations]);

  const formatTimestamp = (ts: string | undefined | null) => {
    if (!ts) return '';
    const date = new Date(ts);
    if (isNaN(date.getTime())) return '';
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return date.toLocaleDateString('en-US', { weekday: 'short' });
    }
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const renderItem = ({ item }: { item: Conversation }) => {
    const photoUri = item.photo ? `https://human-me.com${item.photo}` : null;

    return (
      <TouchableOpacity
        style={styles.conversationRow}
        onPress={() => router.push(`/chat/${item.user_id}`)}
        activeOpacity={0.7}
      >
        <Avatar uri={photoUri} name={item.name} size={50} />
        <View style={styles.conversationBody}>
          <View style={styles.conversationTop}>
            <Text style={styles.conversationName} numberOfLines={1}>
              {item.name}
            </Text>
            <Text style={styles.conversationTime}>{formatTimestamp(item.timestamp)}</Text>
          </View>
          <View style={styles.conversationBottom}>
            <Text style={styles.conversationMessage} numberOfLines={1}>
              {item.last_message || 'No messages yet'}
            </Text>
            {item.unread > 0 && (
              <View style={styles.unreadBadge}>
                <Text style={styles.unreadText}>{item.unread > 99 ? '99+' : item.unread}</Text>
              </View>
            )}
          </View>
        </View>
      </TouchableOpacity>
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
      <Text style={styles.screenTitle}>{t('messages')}</Text>
      <FlatList
        data={conversations}
        keyExtractor={item => String(item.user_id)}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />}
        ListEmptyComponent={
          <EmptyState
            icon="chat-bubble-outline"
            title={t('noConversations')}
            subtitle={t('startChatting')}
          />
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
  screenTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  listContent: {
    paddingBottom: 20,
  },
  conversationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  conversationBody: {
    flex: 1,
    marginLeft: 12,
  },
  conversationTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  conversationName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    flex: 1,
    marginRight: 8,
  },
  conversationTime: {
    fontSize: 12,
    color: '#9ca3af',
  },
  conversationBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  conversationMessage: {
    fontSize: 14,
    color: '#6b7280',
    flex: 1,
    marginRight: 8,
  },
  unreadBadge: {
    backgroundColor: '#3f4a36',
    borderRadius: 12,
    minWidth: 22,
    height: 22,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
  },
  unreadText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
  },
});
