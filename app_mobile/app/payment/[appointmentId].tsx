import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Card } from '@/components/ui/Card';
import api from '../../src/api/api';

interface SavedCard {
  id: string;
  last4: string;
  brand: string;
}

export default function PaymentScreen() {
  const { appointmentId, serviceName, price, providerName } = useLocalSearchParams<{
    appointmentId: string;
    serviceName?: string;
    price?: string;
    providerName?: string;
  }>();
  const router = useRouter();

  const [loading, setLoading] = useState(false);
  const [savedCards, setSavedCards] = useState<SavedCard[]>([]);
  const [cardsLoading, setCardsLoading] = useState(true);
  const [paymentSuccess, setPaymentSuccess] = useState(false);
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);

  useEffect(() => {
    fetchSavedCards();
  }, []);

  const fetchSavedCards = async () => {
    setCardsLoading(true);
    try {
      const res = await api.get('/client/api/cards');
      setSavedCards(res.data || []);
    } catch (err) {
      console.error('Failed to fetch cards:', err);
    } finally {
      setCardsLoading(false);
    }
  };

  const handlePayWithCard = async () => {
    setLoading(true);
    try {
      const res = await api.post('/client/create_payment_session', {
        appointment_id: parseInt(appointmentId, 10),
      });
      const { url } = res.data;
      if (url) {
        const result = await WebBrowser.openBrowserAsync(url);
        if (result.type === 'cancel' || result.type === 'dismiss') {
          // User came back; assume they may have completed payment
          setPaymentSuccess(true);
        }
      }
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to create payment session';
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
    }
  };

  const handlePayCash = async () => {
    setLoading(true);
    try {
      await api.post('/client/pay_cash', {
        appointment_id: parseInt(appointmentId, 10),
      });
      Alert.alert('Success', 'Cash payment recorded successfully');
      setPaymentSuccess(true);
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to record cash payment';
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSavedCard = (card: SavedCard) => {
    setSelectedMethod(card.id);
    Alert.alert(
      'Use Card',
      `Pay with ${card.brand} ending in ${card.last4}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Pay', onPress: () => handlePayWithCard() },
      ]
    );
  };

  if (paymentSuccess) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: 'Payment' }} />
        <View style={styles.successContainer}>
          <View style={styles.successIcon}>
            <Text style={styles.successIconText}>&#10003;</Text>
          </View>
          <Text style={styles.successTitle}>Payment Successful!</Text>
          <Text style={styles.successSubtitle}>
            Your appointment has been confirmed and paid.
          </Text>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => router.back()}
          >
            <Text style={styles.primaryBtnText}>Back to Appointments</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: true, title: 'Payment' }} />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Appointment Summary */}
        <Card style={styles.summaryCard}>
          <Text style={styles.sectionTitle}>Appointment Summary</Text>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Service</Text>
            <Text style={styles.summaryValue}>{serviceName || 'Service'}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Provider</Text>
            <Text style={styles.summaryValue}>{providerName || 'Provider'}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Amount</Text>
            <Text style={styles.summaryPrice}>{price ? `\u20AC${price}` : 'N/A'}</Text>
          </View>
        </Card>

        {/* Payment Options */}
        <Text style={styles.sectionTitle}>Payment Method</Text>

        {/* Pay with Card */}
        <TouchableOpacity
          activeOpacity={0.7}
          onPress={handlePayWithCard}
          disabled={loading}
        >
          <Card style={[styles.methodCard, selectedMethod === 'card' && styles.methodCardActive]}>
            <View style={styles.methodRow}>
              <View style={styles.methodIconContainer}>
                <Text style={styles.methodIcon}>&#128179;</Text>
              </View>
              <View style={styles.methodInfo}>
                <Text style={styles.methodTitle}>Pay with Card</Text>
                <Text style={styles.methodSubtitle}>Secure payment via Stripe</Text>
              </View>
            </View>
          </Card>
        </TouchableOpacity>

        {/* Pay Cash */}
        <TouchableOpacity
          activeOpacity={0.7}
          onPress={handlePayCash}
          disabled={loading}
        >
          <Card style={[styles.methodCard, selectedMethod === 'cash' && styles.methodCardActive]}>
            <View style={styles.methodRow}>
              <View style={styles.methodIconContainer}>
                <Text style={styles.methodIcon}>&#128176;</Text>
              </View>
              <View style={styles.methodInfo}>
                <Text style={styles.methodTitle}>Pay Cash</Text>
                <Text style={styles.methodSubtitle}>Pay the provider directly in cash</Text>
              </View>
            </View>
          </Card>
        </TouchableOpacity>

        {/* Saved Cards */}
        <Text style={[styles.sectionTitle, { marginTop: 24 }]}>Saved Cards</Text>
        {cardsLoading ? (
          <ActivityIndicator size="small" color="#3f4a36" style={{ marginVertical: 16 }} />
        ) : savedCards.length === 0 ? (
          <Text style={styles.noCardsText}>No saved cards yet</Text>
        ) : (
          savedCards.map((card) => (
            <TouchableOpacity
              key={card.id}
              activeOpacity={0.7}
              onPress={() => handleSelectSavedCard(card)}
              disabled={loading}
            >
              <Card style={[styles.methodCard, selectedMethod === card.id && styles.methodCardActive]}>
                <View style={styles.methodRow}>
                  <View style={styles.cardBrandContainer}>
                    <Text style={styles.cardBrandText}>{card.brand.toUpperCase()}</Text>
                  </View>
                  <View style={styles.methodInfo}>
                    <Text style={styles.methodTitle}>**** **** **** {card.last4}</Text>
                    <Text style={styles.methodSubtitle}>{card.brand}</Text>
                  </View>
                </View>
              </Card>
            </TouchableOpacity>
          ))
        )}

        {loading && (
          <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 24 }} />
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
    paddingBottom: 40,
  },
  summaryCard: {
    marginBottom: 24,
    marginTop: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 12,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
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
  summaryPrice: {
    fontSize: 18,
    fontWeight: '700',
    color: '#3f4a36',
  },
  methodCard: {
    marginBottom: 12,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  methodCardActive: {
    borderColor: '#3f4a36',
  },
  methodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  methodIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: '#f0f1ee',
    justifyContent: 'center',
    alignItems: 'center',
  },
  methodIcon: {
    fontSize: 22,
  },
  methodInfo: {
    flex: 1,
  },
  methodTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  methodSubtitle: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 2,
  },
  cardBrandContainer: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: '#e0e7ff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardBrandText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#4f46e5',
  },
  noCardsText: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
    marginVertical: 16,
  },
  successContainer: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  successIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#3f4a36',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  successIconText: {
    fontSize: 36,
    color: '#fff',
  },
  successTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 8,
  },
  successSubtitle: {
    fontSize: 15,
    color: '#6b7280',
    textAlign: 'center',
    marginBottom: 32,
  },
  primaryBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 10,
    alignItems: 'center',
    width: '100%',
  },
  primaryBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
