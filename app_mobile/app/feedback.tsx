import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { useI18n } from '@/contexts/I18nContext';
import api from '../src/api/api';

type FeedbackType = 'bug' | 'suggestion';

export default function FeedbackScreen() {
  const { t } = useI18n();
  const router = useRouter();

  const [feedbackType, setFeedbackType] = useState<FeedbackType>('bug');
  const [feedbackText, setFeedbackText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!feedbackText.trim()) return;

    setSubmitting(true);
    try {
      await api.post('/api/feedback', {
        text: feedbackText.trim(),
        type: feedbackType,
      });
      Alert.alert(t('success'), t('feedbackSent'));
      router.back();
    } catch (err: any) {
      const msg = err.response?.data?.msg || t('error');
      Alert.alert(t('error'), msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ headerShown: true, title: t('feedback') }} />

      <View style={styles.content}>
        {/* Type Toggle */}
        <View style={styles.toggleRow}>
          <TouchableOpacity
            style={[styles.toggleBtn, feedbackType === 'bug' && styles.toggleBtnActive]}
            onPress={() => setFeedbackType('bug')}
            activeOpacity={0.7}
          >
            <Text style={[styles.toggleText, feedbackType === 'bug' && styles.toggleTextActive]}>
              Bug
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.toggleBtn, feedbackType === 'suggestion' && styles.toggleBtnActive]}
            onPress={() => setFeedbackType('suggestion')}
            activeOpacity={0.7}
          >
            <Text style={[styles.toggleText, feedbackType === 'suggestion' && styles.toggleTextActive]}>
              Suggestion
            </Text>
          </TouchableOpacity>
        </View>

        {/* Text Input */}
        <TextInput
          style={styles.textArea}
          value={feedbackText}
          onChangeText={setFeedbackText}
          placeholder={t('feedbackPlaceholder')}
          placeholderTextColor="#9ca3af"
          multiline
          numberOfLines={8}
          textAlignVertical="top"
          maxLength={2000}
        />

        {/* Submit Button */}
        <TouchableOpacity
          style={[styles.submitBtn, (!feedbackText.trim() || submitting) && styles.submitBtnDisabled]}
          onPress={handleSubmit}
          disabled={!feedbackText.trim() || submitting}
          activeOpacity={0.7}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.submitBtnText}>{t('sendFeedback')}</Text>
          )}
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
  content: {
    flex: 1,
    paddingHorizontal: 20,
    paddingTop: 20,
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    backgroundColor: '#f3f4f6',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  toggleBtnActive: {
    backgroundColor: '#3f4a36',
    borderColor: '#3f4a36',
  },
  toggleText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#374151',
  },
  toggleTextActive: {
    color: '#fff',
  },
  textArea: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 15,
    color: '#1f2937',
    minHeight: 180,
    marginBottom: 24,
  },
  submitBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  submitBtnDisabled: {
    backgroundColor: '#9ca3af',
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
