import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
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
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';
import type { AppointmentEvent, ClientRequest } from '../../src/api/types';

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'muted';
type TabMode = 'appointments' | 'requests';

function getStatusBadge(status: string): { label: string; variant: BadgeVariant } {
  switch (status) {
    case 'scheduled':
      return { label: 'Scheduled', variant: 'info' };
    case 'confirmed':
      return { label: 'Confirmed', variant: 'warning' };
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

function getRequestStatusBadge(status: string): { label: string; variant: BadgeVariant } {
  switch (status) {
    case 'open':
      return { label: 'Open', variant: 'info' };
    case 'accepted':
      return { label: 'Accepted', variant: 'success' };
    case 'closed':
      return { label: 'Closed', variant: 'muted' };
    case 'cancelled':
      return { label: 'Cancelled', variant: 'error' };
    default:
      return { label: status, variant: 'muted' };
  }
}

export default function ClientAppointmentsScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<TabMode>('appointments');
  const [appointments, setAppointments] = useState<AppointmentEvent[]>([]);
  const [requests, setRequests] = useState<ClientRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offersModalVisible, setOffersModalVisible] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<ClientRequest | null>(null);
  const [counterOfferId, setCounterOfferId] = useState<number | null>(null);
  const [counterPrice, setCounterPrice] = useState('');
  const [disputeModalVisible, setDisputeModalVisible] = useState(false);
  const [disputeAppointmentId, setDisputeAppointmentId] = useState<number | null>(null);
  const [disputeReason, setDisputeReason] = useState<'not_completed' | 'quality_issue' | 'other'>('other');
  const [disputeDescription, setDisputeDescription] = useState('');

  const fetchAppointments = useCallback(async () => {
    try {
      const res = await api.get('/client/get_appointments');
      const raw = res.data;
      const items = Array.isArray(raw) ? raw : (raw?.data ?? raw?.appointments ?? []);
      setAppointments(items);
    } catch (err: any) {
      console.error('Failed to fetch appointments:', err);
      setError(err.response?.data?.error || err.message || 'Failed to load appointments');
    }
  }, []);

  const fetchRequests = useCallback(async () => {
    try {
      const res = await api.get('/client/client_get_requests');
      const raw = res.data;
      const items = Array.isArray(raw) ? raw : (raw?.requests ?? raw?.data ?? []);
      setRequests(items);
    } catch (err: any) {
      console.error('Failed to fetch requests:', err);
      setError(err.response?.data?.error || err.message || 'Failed to load requests');
    }
  }, []);

  const loadData = useCallback(async () => {
    setError(null);
    setLoading(true);
    await Promise.all([fetchAppointments(), fetchRequests()]);
    setLoading(false);
  }, [fetchAppointments, fetchRequests]);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchAppointments(), fetchRequests()]);
    setRefreshing(false);
  }, [fetchAppointments, fetchRequests]);

  const handleCancelAppointment = useCallback(
    (appointmentId: number) => {
      Alert.alert(t('cancelAppointment'), t('confirmCancelAppointment'), [
        { text: t('cancel'), style: 'cancel' },
        {
          text: t('confirm'),
          style: 'destructive',
          onPress: async () => {
            try {
              await api.post('/client/cancel_appointment', {
                appointment_id: appointmentId,
              });
              Alert.alert(t('success'), t('appointmentCancelled'));
              await fetchAppointments();
            } catch (err) {
              console.error('Failed to cancel appointment:', err);
            }
          },
        },
      ]);
    },
    [t, fetchAppointments]
  );

  const handleCancelRequest = useCallback(
    (requestId: number) => {
      Alert.alert(t('cancelRequest'), t('confirmCancelRequest'), [
        { text: t('cancel'), style: 'cancel' },
        {
          text: t('confirm'),
          style: 'destructive',
          onPress: async () => {
            try {
              await api.post('/client/client_cancel_request', {
                request_id: requestId,
              });
              Alert.alert(t('success'), t('requestCancelled'));
              await fetchRequests();
            } catch (err) {
              console.error('Failed to cancel request:', err);
            }
          },
        },
      ]);
    },
    [t, fetchRequests]
  );

  const handleCompleteAppointment = useCallback(
    async (appointmentId: number) => {
      try {
        await api.post('/client/complete_appointment', {
          appointment_id: appointmentId,
        });
        Alert.alert(t('success'), t('appointmentCompleted'));
        await fetchAppointments();
      } catch (err) {
        console.error('Failed to complete appointment:', err);
      }
    },
    [t, fetchAppointments]
  );

  const handleUndoCancel = useCallback(
    async (appointmentId: number) => {
      try {
        await api.post('/client/undo_cancel_appointment', {
          appointment_id: appointmentId,
        });
        Alert.alert(t('success'), t('undoCancelSuccess'));
        await fetchAppointments();
      } catch (err) {
        console.error('Failed to undo cancel:', err);
      }
    },
    [t, fetchAppointments]
  );

  const handleAcceptOffer = useCallback(
    async (offerId: number) => {
      try {
        await api.post(`/client/client_accept_request/${offerId}`);
        Alert.alert(t('success'), t('offerAccepted'));
        setOffersModalVisible(false);
        setSelectedRequest(null);
        await fetchRequests();
      } catch (err) {
        console.error('Failed to accept offer:', err);
      }
    },
    [t, fetchRequests]
  );

  const handleCounterOffer = useCallback(
    async (offerId: number) => {
      if (!counterPrice.trim()) return;
      try {
        await api.post(`/client/counter_offer/${offerId}`, {
          counter_price: parseFloat(counterPrice),
        });
        Alert.alert(t('success'), t('counterOfferSent'));
        setCounterOfferId(null);
        setCounterPrice('');
        setOffersModalVisible(false);
        setSelectedRequest(null);
        await fetchRequests();
      } catch (err) {
        console.error('Failed to send counter offer:', err);
      }
    },
    [t, counterPrice, fetchRequests]
  );

  const handleProviderNoShow = useCallback(
    (appointmentId: number) => {
      Alert.alert(
        t('providerNoShow') || 'Provider No-Show',
        t('confirmProviderNoShow') || 'Confirm that the provider did not show up? You will receive a full refund.',
        [
          { text: t('cancel'), style: 'cancel' },
          {
            text: t('confirm'),
            style: 'destructive',
            onPress: async () => {
              try {
                await api.post('/client/report_no_show_provider', { appointment_id: appointmentId });
                Alert.alert(t('success'), t('providerNoShowRecorded') || 'Provider no-show recorded. Full refund issued.');
                await fetchAppointments();
              } catch (err: any) {
                Alert.alert(t('error'), err.response?.data?.message || 'Failed');
              }
            },
          },
        ]
      );
    },
    [t, fetchAppointments]
  );

  const handleSubmitDispute = useCallback(async () => {
    if (!disputeAppointmentId) return;
    try {
      await api.post('/client/dispute', {
        appointment_id: disputeAppointmentId,
        reason: disputeReason,
        description: disputeDescription,
      });
      Alert.alert(t('success'), t('disputeCreated') || 'Dispute created');
      setDisputeModalVisible(false);
      setDisputeAppointmentId(null);
      setDisputeDescription('');
      await fetchAppointments();
    } catch (err: any) {
      Alert.alert(t('error'), err.response?.data?.message || 'Failed');
    }
  }, [disputeAppointmentId, disputeReason, disputeDescription, t, fetchAppointments]);

  const isNoShowEligible = (item: AppointmentEvent) => {
    const apptTime = new Date(item.start);
    const now = new Date();
    return now.getTime() > apptTime.getTime() + 15 * 60 * 1000;
  };

  const renderAppointment = ({ item }: { item: AppointmentEvent }) => {
    const { status, service_name, provider_name, amount } = item.extendedProps;
    const appointmentId = item.id;
    const badge = getStatusBadge(status);
    const startDate = new Date(item.start);

    return (
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{service_name}</Text>
            <Text style={styles.cardSubtitle}>{provider_name || 'Provider'}</Text>
          </View>
          <Badge label={badge.label} variant={badge.variant} />
        </View>
        <View style={styles.cardDetails}>
          <Text style={styles.dateText}>
            {startDate.toLocaleDateString('en-US', {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
            })}
            {' '}
            {startDate.toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
          {amount && <Text style={styles.amountText}>${amount}</Text>}
        </View>
        {/* Action Buttons */}
        {status === 'confirmed' && (
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() =>
              router.push({
                pathname: '/payment/[appointmentId]',
                params: {
                  appointmentId: String(appointmentId),
                  serviceName: service_name,
                  price: amount,
                  providerName: provider_name || 'Provider',
                },
              } as any)
            }
          >
            <Text style={styles.actionBtnText}>{t('pay')}</Text>
          </TouchableOpacity>
        )}
        {status === 'completed' && (
          <TouchableOpacity
            style={styles.reviewBtn}
            onPress={() =>
              router.push(`/review/${appointmentId}` as any)
            }
          >
            <Text style={styles.reviewBtnText}>{t('leaveReview')}</Text>
          </TouchableOpacity>
        )}
        {(status === 'scheduled' || status === 'confirmed') && (
          <TouchableOpacity
            style={styles.cancelBtn}
            onPress={() => handleCancelAppointment(appointmentId)}
          >
            <Text style={styles.cancelBtnText}>{t('cancelAppointment')}</Text>
          </TouchableOpacity>
        )}
        {status === 'confirmed_paid' && isNoShowEligible(item) && (
          <TouchableOpacity
            style={[styles.cancelBtn, { borderColor: '#6b7280' }]}
            onPress={() => handleProviderNoShow(appointmentId)}
          >
            <Text style={[styles.cancelBtnText, { color: '#6b7280' }]}>{t('providerNoShow') || 'Provider No-Show'}</Text>
          </TouchableOpacity>
        )}
        {status === 'work_submitted' && (
          <>
            <TouchableOpacity
              style={styles.actionBtn}
              onPress={() => handleCompleteAppointment(appointmentId)}
            >
              <Text style={styles.actionBtnText}>{t('completeAppointment')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.cancelBtn, { borderColor: '#f97316' }]}
              onPress={() => {
                setDisputeAppointmentId(appointmentId);
                setDisputeReason('other');
                setDisputeDescription('');
                setDisputeModalVisible(true);
              }}
            >
              <Text style={[styles.cancelBtnText, { color: '#f97316' }]}>{t('reportIssue') || 'Report Issue'}</Text>
            </TouchableOpacity>
          </>
        )}
        {status === 'cancelled' && (
          <TouchableOpacity
            style={styles.reviewBtn}
            onPress={() => handleUndoCancel(appointmentId)}
          >
            <Text style={styles.reviewBtnText}>{t('undoCancel')}</Text>
          </TouchableOpacity>
        )}
      </Card>
    );
  };

  const renderRequest = ({ item }: { item: ClientRequest }) => {
    const badge = getRequestStatusBadge(item.status);
    const date = new Date(item.appointment_start_time);

    return (
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{item.service_name}</Text>
            <Text style={styles.dateText}>
              {date.toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
              })}
            </Text>
          </View>
          <View style={styles.badgeColumn}>
            <Badge label={badge.label} variant={badge.variant} />
            {item.offers.length > 0 && (
              <TouchableOpacity
                style={styles.offerBadge}
                onPress={() => {
                  setSelectedRequest(item);
                  setCounterOfferId(null);
                  setCounterPrice('');
                  setOffersModalVisible(true);
                }}
              >
                <Text style={styles.offerBadgeText}>
                  {item.offers.length} offer{item.offers.length !== 1 ? 's' : ''}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
        {item.payment > 0 && (
          <Text style={styles.amountText}>${item.payment.toFixed(2)}</Text>
        )}
        {item.status === 'open' && (
          <TouchableOpacity
            style={styles.cancelBtn}
            onPress={() => handleCancelRequest(item.id)}
          >
            <Text style={styles.cancelBtnText}>{t('cancelRequest')}</Text>
          </TouchableOpacity>
        )}
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
      {/* Segment Buttons */}
      <View style={styles.segmentContainer}>
        <View style={styles.segmentRow}>
          <TouchableOpacity
            style={[styles.segmentBtn, activeTab === 'appointments' && styles.segmentBtnActive]}
            onPress={() => setActiveTab('appointments')}
            activeOpacity={0.7}
          >
            <Text
              style={[
                styles.segmentText,
                activeTab === 'appointments' && styles.segmentTextActive,
              ]}
            >
              {t('appointments')}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.segmentBtn, activeTab === 'requests' && styles.segmentBtnActive]}
            onPress={() => setActiveTab('requests')}
            activeOpacity={0.7}
          >
            <Text
              style={[
                styles.segmentText,
                activeTab === 'requests' && styles.segmentTextActive,
              ]}
            >
              {t('myRequests')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {error && (
        <View style={{ padding: 20, alignItems: 'center' }}>
          <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12 }}>{error}</Text>
          <TouchableOpacity onPress={loadData} style={{ backgroundColor: '#3f4a36', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 }}>
            <Text style={{ color: '#fff', fontWeight: '600' }}>{t('retry') || 'Retry'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {activeTab === 'appointments' ? (
        <FlatList
          data={appointments}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderAppointment}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />
          }
          ListEmptyComponent={
            <EmptyState
              icon="event"
              title={t('noBookings')}
              subtitle={t('bookServiceToSeeAppointments') || 'Book a service to see your appointments here'}
            />
          }
        />
      ) : (
        <FlatList
          data={requests}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderRequest}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3f4a36" />
          }
          ListEmptyComponent={
            <EmptyState
              icon="description"
              title={t('noRequests')}
              subtitle={t('createRequestToFind') || 'Create a request to find a provider'}
            />
          }
        />
      )}

      {/* Dispute Modal */}
      <Modal
        visible={disputeModalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setDisputeModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('reportIssue') || 'Report Issue'}</Text>
              <TouchableOpacity onPress={() => setDisputeModalVisible(false)}>
                <Text style={styles.modalCloseText}>X</Text>
              </TouchableOpacity>
            </View>

            <Text style={{ fontSize: 14, color: '#374151', marginBottom: 8 }}>{t('selectReason') || 'Select reason:'}</Text>
            {(['not_completed', 'quality_issue', 'other'] as const).map((reason) => (
              <TouchableOpacity
                key={reason}
                style={{
                  flexDirection: 'row', alignItems: 'center', paddingVertical: 8,
                  paddingHorizontal: 12, borderRadius: 8, marginBottom: 4,
                  backgroundColor: disputeReason === reason ? '#f0f1ee' : 'transparent',
                }}
                onPress={() => setDisputeReason(reason)}
              >
                <View style={{
                  width: 18, height: 18, borderRadius: 9, borderWidth: 2,
                  borderColor: disputeReason === reason ? '#3f4a36' : '#d1d5db',
                  backgroundColor: disputeReason === reason ? '#3f4a36' : 'transparent',
                  marginRight: 10,
                }} />
                <Text style={{ fontSize: 14, color: '#1f2937' }}>
                  {reason === 'not_completed' ? (t('notCompleted') || 'Not Completed') :
                   reason === 'quality_issue' ? (t('qualityIssue') || 'Quality Issue') :
                   (t('other') || 'Other')}
                </Text>
              </TouchableOpacity>
            ))}

            <TextInput
              style={{
                borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8,
                padding: 12, fontSize: 14, minHeight: 80, marginTop: 12,
                textAlignVertical: 'top',
              }}
              placeholder={t('describeIssue') || 'Describe the issue...'}
              multiline
              value={disputeDescription}
              onChangeText={setDisputeDescription}
            />

            <TouchableOpacity
              style={{
                backgroundColor: '#f97316', paddingVertical: 12, borderRadius: 8,
                alignItems: 'center', marginTop: 16,
              }}
              onPress={handleSubmitDispute}
            >
              <Text style={{ color: '#fff', fontWeight: '600', fontSize: 15 }}>{t('submitDispute') || 'Submit Dispute'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Offers Modal */}
      <Modal
        visible={offersModalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => {
          setOffersModalVisible(false);
          setSelectedRequest(null);
          setCounterOfferId(null);
          setCounterPrice('');
        }}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('viewOffers')}</Text>
              <TouchableOpacity
                onPress={() => {
                  setOffersModalVisible(false);
                  setSelectedRequest(null);
                  setCounterOfferId(null);
                  setCounterPrice('');
                }}
              >
                <Text style={styles.modalCloseText}>X</Text>
              </TouchableOpacity>
            </View>
            <FlatList
              data={selectedRequest?.offers || []}
              keyExtractor={(offer) => String(offer.offer_id)}
              renderItem={({ item: offer }) => (
                <View style={styles.offerCard}>
                  <Text style={styles.offerProviderName}>
                    {t('offerFrom')}: {offer.provider_name}
                  </Text>
                  <Text style={styles.offerPrice}>
                    {t('proposedPrice')}: ${offer.proposed_price}
                  </Text>
                  <View style={styles.offerActions}>
                    <TouchableOpacity
                      style={styles.acceptBtn}
                      onPress={() => handleAcceptOffer(offer.offer_id)}
                    >
                      <Text style={styles.actionBtnText}>{t('acceptOffer')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.counterBtn}
                      onPress={() => {
                        setCounterOfferId(counterOfferId === offer.offer_id ? null : offer.offer_id);
                        setCounterPrice('');
                      }}
                    >
                      <Text style={styles.counterBtnText}>{t('counterOffer')}</Text>
                    </TouchableOpacity>
                  </View>
                  {counterOfferId === offer.offer_id && (
                    <View style={styles.counterInputRow}>
                      <TextInput
                        style={styles.counterInput}
                        placeholder={t('yourCounterPrice')}
                        keyboardType="numeric"
                        value={counterPrice}
                        onChangeText={setCounterPrice}
                      />
                      <TouchableOpacity
                        style={styles.counterSubmitBtn}
                        onPress={() => handleCounterOffer(offer.offer_id)}
                      >
                        <Text style={styles.actionBtnText}>{t('confirm')}</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              )}
              ListEmptyComponent={
                <Text style={styles.emptyOffersText}>{t('noOffersYet') || 'No offers yet'}</Text>
              }
            />
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
  segmentContainer: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  segmentRow: {
    flexDirection: 'row',
    backgroundColor: '#e5e7eb',
    borderRadius: 10,
    padding: 3,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  segmentBtnActive: {
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  segmentText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  segmentTextActive: {
    color: '#3f4a36',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  card: {
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  cardSubtitle: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 2,
  },
  cardDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  dateText: {
    fontSize: 14,
    color: '#374151',
    fontWeight: '500',
  },
  amountText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3f4a36',
  },
  badgeColumn: {
    alignItems: 'flex-end',
    gap: 4,
  },
  offerBadge: {
    backgroundColor: '#3f4a36',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  offerBadgeText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  actionBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 12,
  },
  actionBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  reviewBtn: {
    backgroundColor: '#f0f1ee',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 12,
  },
  reviewBtnText: {
    color: '#3f4a36',
    fontSize: 14,
    fontWeight: '600',
  },
  cancelBtn: {
    borderWidth: 1.5,
    borderColor: '#dc2626',
    backgroundColor: 'transparent',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 12,
  },
  cancelBtnText: {
    color: '#dc2626',
    fontSize: 14,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
  },
  modalCloseText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#6b7280',
    paddingHorizontal: 8,
  },
  offerCard: {
    backgroundColor: '#f9fafb',
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  offerProviderName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  offerPrice: {
    fontSize: 14,
    color: '#374151',
    marginBottom: 10,
  },
  offerActions: {
    flexDirection: 'row',
    gap: 10,
  },
  acceptBtn: {
    flex: 1,
    backgroundColor: '#3f4a36',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  counterBtn: {
    flex: 1,
    backgroundColor: '#f0f1ee',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  counterBtnText: {
    color: '#3f4a36',
    fontSize: 14,
    fontWeight: '600',
  },
  counterInputRow: {
    flexDirection: 'row',
    marginTop: 10,
    gap: 10,
  },
  counterInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    backgroundColor: '#fff',
  },
  counterSubmitBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyOffersText: {
    textAlign: 'center',
    color: '#6b7280',
    fontSize: 14,
    paddingVertical: 20,
  },
});
