import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Avatar } from '@/components/ui/Avatar';
import { Badge } from '@/components/ui/Badge';
import { StarRating } from '@/components/ui/StarRating';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import api from '../../src/api/api';
import type { ProviderService, Review, CancellationPolicyInfo } from '../../src/api/types';

export default function ProviderDetailScreen() {
  const { providerId } = useLocalSearchParams<{ providerId: string }>();
  const router = useRouter();

  const [services, setServices] = useState<ProviderService[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [policy, setPolicy] = useState<CancellationPolicyInfo | null>(null);
  const [providerInfo, setProviderInfo] = useState<{
    name: string;
    photo: string | null;
    online: boolean;
    verified: boolean;
    avg_rating: number;
    review_count: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [policyExpanded, setPolicyExpanded] = useState(false);

  useEffect(() => {
    loadProviderData();
  }, [providerId]);

  const loadProviderData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [servicesRes, reviewsRes, policyRes] = await Promise.all([
        api.get(`/client/get_provider_services?provider_id=${providerId}`),
        api.get(`/client/get_reviews/${providerId}`),
        api.get(`/client/get_provider_policy?provider_id=${providerId}`),
      ]);

      const sRaw = servicesRes.data;
      setServices(Array.isArray(sRaw) ? sRaw : Array.isArray(sRaw?.services) ? sRaw.services : Array.isArray(sRaw?.data) ? sRaw.data : []);

      const reviewData = reviewsRes.data;
      const rRaw = reviewData?.reviews || reviewData?.data || reviewData;
      setReviews(Array.isArray(rRaw) ? rRaw : []);

      // Extract provider info from reviews or services response
      if (reviewData?.provider) {
        setProviderInfo(reviewData.provider);
      } else if (servicesRes.data?.provider) {
        setProviderInfo(servicesRes.data.provider);
      }

      setPolicy(policyRes.data || null);
    } catch (err: any) {
      console.error('Failed to load provider data:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load provider data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ title: 'Provider' }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ title: 'Provider' }} />
        <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12, textAlign: 'center', paddingHorizontal: 20 }}>{error}</Text>
        <TouchableOpacity style={{ backgroundColor: '#3f4a36', paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8 }} onPress={loadProviderData}>
          <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>Retry</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  const photoUri = providerInfo?.photo ? `https://human-me.com${providerInfo.photo}` : null;
  const avgRating = providerInfo?.avg_rating || 0;
  const reviewCount = providerInfo?.review_count || reviews.length;

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ title: providerInfo?.name || 'Provider' }} />
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.headerSection}>
          <Avatar uri={photoUri} name={providerInfo?.name} size={100} online={providerInfo?.online} />
          <Text style={styles.providerName}>{providerInfo?.name || 'Provider'}</Text>
          <View style={styles.ratingRow}>
            <StarRating rating={avgRating} size={20} />
            <Text style={styles.ratingText}>
              {avgRating.toFixed(1)} ({reviewCount} review{reviewCount !== 1 ? 's' : ''})
            </Text>
          </View>
          <View style={styles.badgeRow}>
            {providerInfo?.online && <Badge label="Online" variant="success" />}
            {providerInfo?.verified && <Badge label="Verified" variant="info" />}
          </View>
        </View>

        {/* Services */}
        <Text style={styles.sectionTitle}>Services</Text>
        {services.length > 0 ? (
          services.map(service => (
            <Card key={service.id} style={styles.serviceCard}>
              <View style={styles.serviceRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.serviceName}>{service.name}</Text>
                  {service.description && (
                    <Text style={styles.serviceDesc} numberOfLines={2}>
                      {service.description}
                    </Text>
                  )}
                </View>
                <View style={styles.serviceMeta}>
                  <Text style={styles.servicePrice}>${service.price}</Text>
                  <Text style={styles.serviceDuration}>{service.duration} min</Text>
                </View>
              </View>
            </Card>
          ))
        ) : (
          <Text style={styles.emptyText}>No services listed</Text>
        )}

        {/* Reviews */}
        <Text style={styles.sectionTitle}>Reviews</Text>
        {reviews.length > 0 ? (
          reviews.map(review => (
            <Card key={review.id} style={styles.reviewCard}>
              <View style={styles.reviewHeader}>
                <StarRating rating={review.rating} size={14} />
                <Text style={styles.reviewDate}>
                  {new Date(review.created_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </Text>
              </View>
              {review.comment && <Text style={styles.reviewComment}>{review.comment}</Text>}
              <Text style={styles.reviewerName}>{review.patient_name}</Text>
              {review.response_text && (
                <View style={styles.responseBlock}>
                  <Text style={styles.responseLabel}>Provider response:</Text>
                  <Text style={styles.responseText}>{review.response_text}</Text>
                </View>
              )}
            </Card>
          ))
        ) : (
          <Text style={styles.emptyText}>No reviews yet</Text>
        )}

        {/* Cancellation Policy */}
        {policy && policy.has_policy && (
          <>
            <TouchableOpacity
              style={styles.policyHeader}
              onPress={() => setPolicyExpanded(!policyExpanded)}
              activeOpacity={0.7}
            >
              <Text style={styles.sectionTitle}>Cancellation Policy</Text>
              <Text style={styles.expandIcon}>{policyExpanded ? '-' : '+'}</Text>
            </TouchableOpacity>
            {policyExpanded && (
              <Card style={styles.policyCard}>
                <Text style={styles.policyText}>{policy.description}</Text>
                {policy.free_cancel_hours !== undefined && (
                  <Text style={styles.policyDetail}>
                    Free cancellation up to {policy.free_cancel_hours} hours before
                  </Text>
                )}
                {policy.late_cancel_fee_percent !== undefined && (
                  <Text style={styles.policyDetail}>
                    Late cancellation fee: {policy.late_cancel_fee_percent}%
                  </Text>
                )}
                {policy.no_show_client_fee_percent !== undefined && (
                  <Text style={styles.policyDetail}>
                    No-show fee: {policy.no_show_client_fee_percent}%
                  </Text>
                )}
              </Card>
            )}
          </>
        )}

        {/* Bottom spacer for floating button */}
        <View style={{ height: 80 }} />
      </ScrollView>

      {/* Floating Book Now Button */}
      <View style={styles.floatingBtnContainer}>
        <TouchableOpacity
          style={styles.bookNowBtn}
          onPress={() => router.push(`/booking/${providerId}`)}
          activeOpacity={0.8}
        >
          <Text style={styles.bookNowBtnText}>Book Now</Text>
        </TouchableOpacity>
      </View>
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
    paddingTop: 16,
    paddingBottom: 20,
  },
  headerSection: {
    alignItems: 'center',
    marginBottom: 24,
  },
  providerName: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1f2937',
    marginTop: 12,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
  },
  ratingText: {
    fontSize: 14,
    color: '#6b7280',
  },
  badgeRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 10,
    marginTop: 8,
  },
  serviceCard: {
    marginBottom: 10,
  },
  serviceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  serviceName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  serviceDesc: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 2,
  },
  serviceMeta: {
    alignItems: 'flex-end',
    marginLeft: 12,
  },
  servicePrice: {
    fontSize: 16,
    fontWeight: '700',
    color: '#3f4a36',
  },
  serviceDuration: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 2,
  },
  reviewCard: {
    marginBottom: 10,
  },
  reviewHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  reviewDate: {
    fontSize: 12,
    color: '#9ca3af',
  },
  reviewComment: {
    fontSize: 14,
    color: '#374151',
    marginBottom: 4,
  },
  reviewerName: {
    fontSize: 13,
    color: '#6b7280',
    fontStyle: 'italic',
  },
  responseBlock: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f3f4f6',
  },
  responseLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: 2,
  },
  responseText: {
    fontSize: 13,
    color: '#374151',
  },
  emptyText: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
    paddingVertical: 16,
  },
  policyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  expandIcon: {
    fontSize: 22,
    fontWeight: '700',
    color: '#6b7280',
    paddingHorizontal: 4,
  },
  policyCard: {
    marginBottom: 10,
  },
  policyText: {
    fontSize: 14,
    color: '#374151',
    marginBottom: 8,
  },
  policyDetail: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 4,
  },
  floatingBtnContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: 16,
    backgroundColor: 'rgba(249, 250, 251, 0.95)',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  bookNowBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  bookNowBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
});
