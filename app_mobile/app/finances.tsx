import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import * as SecureStore from 'expo-secure-store';
import { Card } from '@/components/ui/Card';
import api from '../src/api/api';

interface FinanceData {
  stripe_connected: boolean;
  available_balance?: number;
  currency?: string;
  bank_last4?: string;
  bank_name?: string;
}

export default function FinancesScreen() {
  const [loading, setLoading] = useState(true);
  const [financeData, setFinanceData] = useState<FinanceData>({
    stripe_connected: false,
  });
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    fetchFinanceData();
  }, []);

  const fetchFinanceData = async () => {
    setLoading(true);
    try {
      const res = await api.get('/provider/stats');
      // Try to extract stripe info from stats response
      if (res.data && typeof res.data === 'object') {
        setFinanceData({
          stripe_connected: res.data.stripe_connected || false,
          available_balance: res.data.available_balance,
          currency: res.data.currency || 'EUR',
          bank_last4: res.data.bank_last4,
          bank_name: res.data.bank_name,
        });
      }
    } catch (err) {
      // Stats endpoint might return HTML, use defaults
      console.error('Failed to fetch finance data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleConnectStripe = async () => {
    setActionLoading(true);
    try {
      const token = await SecureStore.getItemAsync('userToken');
      const url = `https://human-me.com/provider/connect_stripe`;
      await WebBrowser.openBrowserAsync(url, {
        createTask: true,
      });
      // Refetch after return
      await fetchFinanceData();
    } catch (err: any) {
      Alert.alert('Error', 'Failed to open Stripe connection page');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStripeDashboard = async () => {
    setActionLoading(true);
    try {
      const res = await api.get('/provider/stripe_login_link');
      const url = res.data?.url;
      if (url) {
        await WebBrowser.openBrowserAsync(url);
      } else {
        // Fallback: open the endpoint directly
        await WebBrowser.openBrowserAsync('https://human-me.com/provider/stripe_login_link');
      }
    } catch (err: any) {
      Alert.alert('Error', 'Failed to open Stripe dashboard');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: 'Finances' }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: true, title: 'Finances' }} />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Stripe Connection Status */}
        <Card style={styles.statusCard}>
          <View style={styles.statusRow}>
            <View style={[
              styles.statusDot,
              financeData.stripe_connected ? styles.statusDotActive : styles.statusDotInactive,
            ]} />
            <Text style={styles.statusText}>
              {financeData.stripe_connected
                ? 'Stripe Connected'
                : 'Stripe Not Connected'}
            </Text>
          </View>
          {!financeData.stripe_connected && (
            <Text style={styles.statusSubtext}>
              Connect your Stripe account to receive payments from clients
            </Text>
          )}
        </Card>

        {financeData.stripe_connected ? (
          <>
            {/* Balance Card */}
            <Card style={styles.balanceCard}>
              <Text style={styles.balanceLabel}>Available Balance</Text>
              <Text style={styles.balanceAmount}>
                {financeData.currency === 'EUR' ? '\u20AC' : '$'}
                {(financeData.available_balance ?? 0).toFixed(2)}
              </Text>
            </Card>

            {/* Bank Info */}
            {financeData.bank_last4 && (
              <Card style={styles.infoCard}>
                <Text style={styles.infoLabel}>Bank Account</Text>
                <View style={styles.bankRow}>
                  <View style={styles.bankIcon}>
                    <Text style={styles.bankIconText}>&#127974;</Text>
                  </View>
                  <View>
                    <Text style={styles.bankName}>{financeData.bank_name || 'Bank Account'}</Text>
                    <Text style={styles.bankLast4}>**** {financeData.bank_last4}</Text>
                  </View>
                </View>
              </Card>
            )}

            {/* Stripe Dashboard Button */}
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={handleStripeDashboard}
              disabled={actionLoading}
            >
              {actionLoading ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={styles.primaryBtnText}>Go to Stripe Dashboard</Text>
              )}
            </TouchableOpacity>
          </>
        ) : (
          <>
            {/* Connect Stripe Button */}
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={handleConnectStripe}
              disabled={actionLoading}
            >
              {actionLoading ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={styles.primaryBtnText}>Connect Stripe Account</Text>
              )}
            </TouchableOpacity>

            {/* Info Section */}
            <Card style={[styles.infoCard, { marginTop: 24 }]}>
              <Text style={styles.infoTitle}>Why Connect Stripe?</Text>
              <View style={styles.infoItem}>
                <Text style={styles.infoBullet}>{'\u2022'}</Text>
                <Text style={styles.infoText}>Accept card payments from clients</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoBullet}>{'\u2022'}</Text>
                <Text style={styles.infoText}>Automatic payouts to your bank account</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoBullet}>{'\u2022'}</Text>
                <Text style={styles.infoText}>Track your earnings and transactions</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoBullet}>{'\u2022'}</Text>
                <Text style={styles.infoText}>Secure and reliable payment processing</Text>
              </View>
            </Card>
          </>
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
    paddingTop: 8,
  },
  statusCard: {
    marginBottom: 16,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statusDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  statusDotActive: {
    backgroundColor: '#22c55e',
  },
  statusDotInactive: {
    backgroundColor: '#ef4444',
  },
  statusText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  statusSubtext: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 8,
  },
  balanceCard: {
    marginBottom: 16,
    backgroundColor: '#3f4a36',
  },
  balanceLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
    marginBottom: 4,
  },
  balanceAmount: {
    fontSize: 36,
    fontWeight: '700',
    color: '#fff',
  },
  infoCard: {
    marginBottom: 16,
  },
  infoLabel: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 12,
  },
  bankRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  bankIcon: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: '#f0f1ee',
    justifyContent: 'center',
    alignItems: 'center',
  },
  bankIconText: {
    fontSize: 20,
  },
  bankName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1f2937',
  },
  bankLast4: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 2,
  },
  primaryBtn: {
    backgroundColor: '#3f4a36',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  primaryBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 12,
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: 8,
  },
  infoBullet: {
    fontSize: 16,
    color: '#3f4a36',
    lineHeight: 22,
  },
  infoText: {
    fontSize: 14,
    color: '#374151',
    flex: 1,
    lineHeight: 22,
  },
});
