import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from 'expo-router';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';

interface AvailableRequest {
  id: number;
  service_name: string;
  district: string;
  appointment_start_time: string;
  payment: number;
  notes: string;
  address: string;
  status: string;
}

interface AcceptedRequest {
  offer_id: number;
  request_id: number;
  service_name: string;
  status: string;
  proposed_price: number;
}

export default function ProviderRequestsScreen() {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<'available' | 'offers'>('available');
  const [availableRequests, setAvailableRequests] = useState<AvailableRequest[]>([]);
  const [acceptedRequests, setAcceptedRequests] = useState<AcceptedRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Send offer modal state
  const [offerModalVisible, setOfferModalVisible] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [offerPrice, setOfferPrice] = useState('');
  const [sendingOffer, setSendingOffer] = useState(false);

  const fetchAvailable = useCallback(async () => {
    try {
      const res = await api.get('/provider/provider_get_requests');
      const raw = res.data;
      const list = Array.isArray(raw) ? raw : Array.isArray(raw?.data) ? raw.data : Array.isArray(raw?.requests) ? raw.requests : [];
      setAvailableRequests(list);
    } catch (err: any) {
      console.error('Failed to fetch available requests:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load requests');
    }
  }, []);

  const fetchAccepted = useCallback(async () => {
    try {
      const res = await api.get('/provider/provider_get_accepted_requests');
      const raw = res.data;
      const list = Array.isArray(raw) ? raw : Array.isArray(raw?.requests) ? raw.requests : Array.isArray(raw?.data) ? raw.data : [];
      setAcceptedRequests(list);
    } catch (err: any) {
      console.error('Failed to fetch accepted requests:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load offers');
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    await Promise.all([fetchAvailable(), fetchAccepted()]);
    setLoading(false);
  }, [fetchAvailable, fetchAccepted]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    if (activeTab === 'available') {
      await fetchAvailable();
    } else {
      await fetchAccepted();
    }
    setRefreshing(false);
  }, [activeTab, fetchAvailable, fetchAccepted]);

  const openOfferModal = (requestId: number) => {
    setSelectedRequestId(requestId);
    setOfferPrice('');
    setOfferModalVisible(true);
  };

  const sendOffer = async () => {
    if (!offerPrice || !selectedRequestId) {
      Alert.alert(t('error'), t('enterPrice'));
      return;
    }
    setSendingOffer(true);
    try {
      await api.post(`/provider/provider_accept_request/${selectedRequestId}`, {
        price: parseFloat(offerPrice),
      });
      Alert.alert(t('success'), t('offerSent'));
      setOfferModalVisible(false);
      await fetchAvailable();
      await fetchAccepted();
    } catch (err: any) {
      const msg = err.response?.data?.msg || t('failedSendOffer');
      Alert.alert(t('error'), msg);
    } finally {
      setSendingOffer(false);
    }
  };

  const withdrawOffer = async (offerId: number) => {
    Alert.alert(t('withdraw'), t('withdrawOffer'), [
      { text: t('cancel'), style: 'cancel' },
      {
        text: t('withdraw'),
        style: 'destructive',
        onPress: async () => {
          try {
            await api.post(`/provider/withdraw_offer/${offerId}`);
            Alert.alert(t('success'), t('offerWithdrawn'));
            await fetchAccepted();
          } catch (err: any) {
            const msg = err.response?.data?.msg || t('failedWithdrawOffer');
            Alert.alert(t('error'), msg);
          }
        },
      },
    ]);
  };

  const renderAvailableItem = ({ item }: { item: AvailableRequest }) => {
    const date = item.appointment_start_time
      ? new Date(item.appointment_start_time).toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })
      : 'Flexible';

    return (
      <Card style={styles.requestCard}>
        <Text style={styles.requestService}>{item.service_name}</Text>
        {item.district ? (
          <Text style={styles.requestDetail}>{item.district}</Text>
        ) : null}
        <Text style={styles.requestDetail}>{date}</Text>
        {item.payment > 0 && (
          <Text style={styles.requestBudget}>{t('budget')}: ${item.payment}</Text>
        )}
        {item.notes ? (
          <Text style={styles.requestNotes} numberOfLines={2}>
            {item.notes}
          </Text>
        ) : null}
        <TouchableOpacity
          style={styles.sendOfferBtn}
          onPress={() => openOfferModal(item.id)}
        >
          <Text style={styles.sendOfferBtnText}>{t('sendOffer')}</Text>
        </TouchableOpacity>
      </Card>
    );
  };

  const renderAcceptedItem = ({ item }: { item: AcceptedRequest }) => {
    return (
      <Card style={styles.requestCard}>
        <View style={styles.acceptedHeader}>
          <Text style={styles.requestService}>{item.service_name}</Text>
          <Badge label={item.status} variant="info" />
        </View>
        <Text style={styles.requestBudget}>{t('yourPrice')}: ${item.proposed_price}</Text>
        <TouchableOpacity
          style={styles.withdrawBtn}
          onPress={() => withdrawOffer(item.offer_id)}
        >
          <Text style={styles.withdrawBtnText}>{t('withdraw')}</Text>
        </TouchableOpacity>
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
      <Text style={styles.screenTitle}>{t('requests')}</Text>

      <View style={styles.tabRow}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'available' && styles.tabActive]}
          onPress={() => setActiveTab('available')}
        >
          <Text style={[styles.tabText, activeTab === 'available' && styles.tabTextActive]}>
            {t('available')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'offers' && styles.tabActive]}
          onPress={() => setActiveTab('offers')}
        >
          <Text style={[styles.tabText, activeTab === 'offers' && styles.tabTextActive]}>
            {t('myOffers')}
          </Text>
        </TouchableOpacity>
      </View>

      {activeTab === 'available' ? (
        <FlatList
          data={availableRequests}
          keyExtractor={item => String(item.id)}
          renderItem={renderAvailableItem}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />}
          ListEmptyComponent={
            <EmptyState icon="assignment" title={t('noRequests')} subtitle={t('checkBackLater')} />
          }
        />
      ) : (
        <FlatList
          data={acceptedRequests}
          keyExtractor={item => String(item.offer_id)}
          renderItem={renderAcceptedItem}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />}
          ListEmptyComponent={
            <EmptyState icon="send" title={t('noOffers')} subtitle={t('browseRequests')} />
          }
        />
      )}

      {/* Send Offer Modal */}
      <Modal visible={offerModalVisible} transparent animationType="slide">
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>{t('sendOffer')}</Text>
            <Text style={styles.modalLabel}>{t('yourPrice')}</Text>
            <TextInput
              style={styles.modalInput}
              placeholder={t('enterYourPrice')}
              keyboardType="numeric"
              value={offerPrice}
              onChangeText={setOfferPrice}
            />
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setOfferModalVisible(false)}
              >
                <Text style={styles.modalCancelText}>{t('cancel')}</Text>
              </TouchableOpacity>
              {sendingOffer ? (
                <ActivityIndicator size="small" color="#3f4a36" />
              ) : (
                <TouchableOpacity style={styles.modalSubmitBtn} onPress={sendOffer}>
                  <Text style={styles.modalSubmitText}>{t('send')}</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </KeyboardAvoidingView>
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
  screenTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  tabRow: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 12,
    gap: 8,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#e5e7eb',
    alignItems: 'center',
  },
  tabActive: {
    backgroundColor: '#3f4a36',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  tabTextActive: {
    color: '#fff',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  requestCard: {
    marginBottom: 12,
  },
  requestService: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  requestDetail: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 2,
  },
  requestBudget: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3f4a36',
    marginTop: 4,
  },
  requestNotes: {
    fontSize: 13,
    color: '#9ca3af',
    marginTop: 4,
    fontStyle: 'italic',
  },
  sendOfferBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignSelf: 'flex-start',
    marginTop: 10,
  },
  sendOfferBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  acceptedHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  withdrawBtn: {
    borderColor: '#ef4444',
    borderWidth: 1,
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignSelf: 'flex-start',
    marginTop: 10,
  },
  withdrawBtnText: {
    color: '#ef4444',
    fontSize: 14,
    fontWeight: '600',
  },
  // Modal
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    width: '85%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 16,
    textAlign: 'center',
  },
  modalLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  modalInput: {
    height: 50,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 15,
    backgroundColor: '#f8f8f8',
    fontSize: 16,
    marginBottom: 16,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
  },
  modalCancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 20,
  },
  modalCancelText: {
    fontSize: 16,
    color: '#6b7280',
    fontWeight: '600',
  },
  modalSubmitBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 10,
    paddingHorizontal: 24,
    borderRadius: 8,
  },
  modalSubmitText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
