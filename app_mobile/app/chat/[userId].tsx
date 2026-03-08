import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Image,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, Stack } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import api from '../../src/api/api';
import type { ChatMessage } from '../../src/api/types';

export default function ChatScreen() {
  const { userId } = useLocalSearchParams<{ userId: string }>();
  const { user } = useAuth();
  const { t } = useI18n();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [chatPartnerName, setChatPartnerName] = useState('Chat');

  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    fetchMessages();
  }, [userId]);

  const fetchMessages = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/messages/${userId}?page=1`);
      const data = res.data;
      const msgList = Array.isArray(data) ? data : Array.isArray(data?.messages) ? data.messages : Array.isArray(data?.data) ? data.data : [];
      setMessages(msgList);
      if (data?.partner_name) {
        setChatPartnerName(data.partner_name);
      }
    } catch (err: any) {
      console.error('Failed to fetch messages:', err);
      setError(err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to load messages');
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    const text = inputText.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      await api.post('/api/send_message', {
        recipient_id: parseInt(userId, 10),
        text,
      });
      setInputText('');

      // Optimistic add
      const newMsg: ChatMessage = {
        id: Date.now(),
        sender_id: user?.id || 0,
        text,
        message_type: 'text',
        file_url: null,
        file_name: null,
        file_size: null,
        timestamp: new Date().toISOString(),
        is_read: false,
        proposal_status: null,
      };
      setMessages(prev => [newMsg, ...prev]);
    } catch (err: any) {
      console.error('Failed to send message:', err);
      Alert.alert('Error', err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const pickAndSendPhoto = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.7,
      });

      if (result.canceled || !result.assets?.length) return;

      setUploadingPhoto(true);
      const asset = result.assets[0];

      const formData = new FormData();
      formData.append('file', {
        uri: asset.uri,
        name: 'photo.jpg',
        type: 'image/jpeg',
      } as any);
      formData.append('recipient_id', userId);
      formData.append('message_type', 'photo');

      const res = await api.post('/api/send_message', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Optimistic add
      const newMsg: ChatMessage = {
        id: Date.now(),
        sender_id: user?.id || 0,
        text: '',
        message_type: 'photo',
        file_url: asset.uri,
        file_name: 'photo.jpg',
        file_size: null,
        timestamp: new Date().toISOString(),
        is_read: false,
        proposal_status: null,
      };
      setMessages(prev => [newMsg, ...prev]);
    } catch (err: any) {
      console.error('Failed to send photo:', err);
      Alert.alert('Error', 'Failed to send photo');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const formatTime = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const formatDateSeparator = (ts: string) => {
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const handleProposalAction = async (messageId: number, action: 'accept' | 'decline') => {
    try {
      await api.post(`/api/proposal/${messageId}/${action}`);
      setMessages(prev =>
        prev.map(msg =>
          msg.id === messageId
            ? { ...msg, proposal_status: action === 'accept' ? 'accepted' : 'declined' }
            : msg
        )
      );
    } catch (err) {
      console.error(`Failed to ${action} proposal:`, err);
      Alert.alert('Error', `Failed to ${action} proposal`);
    }
  };

  const renderMessage = ({ item, index }: { item: ChatMessage; index: number }) => {
    const isSent = item.sender_id === user?.id;

    // Show date separator if day changes
    let showDateSep = false;
    if (index === messages.length - 1) {
      showDateSep = true;
    } else {
      const current = new Date(item.timestamp).toDateString();
      const next = new Date(messages[index + 1].timestamp).toDateString();
      if (current !== next) {
        showDateSep = true;
      }
    }

    if (item.message_type === 'proposal') {
      return (
        <View>
          {showDateSep && (
            <View style={styles.dateSeparator}>
              <Text style={styles.dateSeparatorText}>{formatDateSeparator(item.timestamp)}</Text>
            </View>
          )}
          <View style={[styles.messageBubbleRow, isSent ? styles.sentRow : styles.receivedRow]}>
            <View style={styles.proposalBubble}>
              <Text style={styles.proposalTitle}>{t('proposal')}</Text>
              <Text style={styles.proposalPrice}>${parseFloat(item.text || '0').toFixed(2)}</Text>
              {item.proposal_status === 'pending' && !isSent && (
                <View style={styles.proposalBtnRow}>
                  <TouchableOpacity
                    style={styles.proposalAcceptBtn}
                    onPress={() => handleProposalAction(item.id, 'accept')}
                  >
                    <Text style={styles.proposalAcceptText}>{t('acceptProposal')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.proposalDeclineBtn}
                    onPress={() => handleProposalAction(item.id, 'decline')}
                  >
                    <Text style={styles.proposalDeclineText}>{t('declineProposal')}</Text>
                  </TouchableOpacity>
                </View>
              )}
              {item.proposal_status === 'accepted' && (
                <Text style={[styles.proposalStatusText, { color: '#16a34a' }]}>{t('proposalAccepted')}</Text>
              )}
              {item.proposal_status === 'declined' && (
                <Text style={[styles.proposalStatusText, { color: '#ef4444' }]}>{t('proposalDeclined')}</Text>
              )}
              <Text style={[styles.messageTime, { color: '#9ca3af' }]}>
                {formatTime(item.timestamp)}
              </Text>
            </View>
          </View>
        </View>
      );
    }

    return (
      <View>
        {showDateSep && (
          <View style={styles.dateSeparator}>
            <Text style={styles.dateSeparatorText}>{formatDateSeparator(item.timestamp)}</Text>
          </View>
        )}
        <View style={[styles.messageBubbleRow, isSent ? styles.sentRow : styles.receivedRow]}>
          <View style={[styles.messageBubble, isSent ? styles.sentBubble : styles.receivedBubble, item.message_type === 'photo' && styles.photoBubble]}>
            {item.message_type === 'photo' && item.file_url ? (
              <Image
                source={{ uri: item.file_url }}
                style={styles.chatImage}
                resizeMode="cover"
              />
            ) : (
              <Text style={[styles.messageText, isSent ? styles.sentText : styles.receivedText]}>
                {item.text}
              </Text>
            )}
            <Text style={[styles.messageTime, isSent ? styles.sentTime : styles.receivedTime]}>
              {formatTime(item.timestamp)}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ title: chatPartnerName }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ title: chatPartnerName }} />
        <Text style={{ color: '#ef4444', fontSize: 16, marginBottom: 12, textAlign: 'center', paddingHorizontal: 20 }}>{error}</Text>
        <TouchableOpacity style={{ backgroundColor: '#3f4a36', paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8 }} onPress={fetchMessages}>
          <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>Retry</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ title: chatPartnerName }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={item => String(item.id)}
          renderItem={renderMessage}
          inverted
          contentContainerStyle={styles.messageList}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={styles.emptyChat}>
              <Text style={styles.emptyChatText}>No messages yet</Text>
              <Text style={styles.emptyChatSubtext}>Send a message to start the conversation</Text>
            </View>
          }
        />

        <View style={styles.inputBar}>
          <TouchableOpacity
            style={styles.attachBtn}
            onPress={pickAndSendPhoto}
            disabled={uploadingPhoto}
          >
            {uploadingPhoto ? (
              <ActivityIndicator size="small" color="#3f4a36" />
            ) : (
              <MaterialIcons name="photo-camera" size={24} color="#3f4a36" />
            )}
          </TouchableOpacity>
          <TextInput
            style={styles.textInput}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type a message..."
            placeholderTextColor="#9ca3af"
            multiline
            maxLength={2000}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!inputText.trim() || sending) && styles.sendBtnDisabled]}
            onPress={sendMessage}
            disabled={!inputText.trim() || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.sendBtnText}>Send</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
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
  messageList: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  dateSeparator: {
    alignItems: 'center',
    marginVertical: 12,
  },
  dateSeparatorText: {
    fontSize: 12,
    color: '#9ca3af',
    backgroundColor: '#e5e7eb',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 10,
    overflow: 'hidden',
  },
  messageBubbleRow: {
    marginBottom: 6,
    flexDirection: 'row',
  },
  sentRow: {
    justifyContent: 'flex-end',
  },
  receivedRow: {
    justifyContent: 'flex-start',
  },
  messageBubble: {
    maxWidth: '78%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
  },
  sentBubble: {
    backgroundColor: '#3f4a36',
    borderBottomRightRadius: 4,
  },
  receivedBubble: {
    backgroundColor: '#e5e7eb',
    borderBottomLeftRadius: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  sentText: {
    color: '#fff',
  },
  receivedText: {
    color: '#1f2937',
  },
  messageTime: {
    fontSize: 11,
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  sentTime: {
    color: 'rgba(255,255,255,0.7)',
  },
  receivedTime: {
    color: '#9ca3af',
  },
  emptyChat: {
    alignItems: 'center',
    paddingTop: 60,
    // Since FlatList is inverted, this appears at the bottom visually
    transform: [{ scaleY: -1 }],
  },
  emptyChatText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#9ca3af',
  },
  emptyChatSubtext: {
    fontSize: 14,
    color: '#d1d5db',
    marginTop: 4,
  },
  photoBubble: {
    paddingHorizontal: 4,
    paddingTop: 4,
    paddingBottom: 6,
  },
  chatImage: {
    width: 200,
    height: 200,
    borderRadius: 12,
  },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    backgroundColor: '#fff',
    gap: 8,
  },
  attachBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textInput: {
    flex: 1,
    minHeight: 40,
    maxHeight: 100,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 8,
    fontSize: 15,
    backgroundColor: '#f8f8f8',
    color: '#1f2937',
  },
  sendBtn: {
    backgroundColor: '#3f4a36',
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: 40,
  },
  sendBtnDisabled: {
    backgroundColor: '#9ca3af',
  },
  sendBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  proposalBubble: {
    backgroundColor: '#f0f1ee',
    borderRadius: 16,
    padding: 14,
    maxWidth: '78%',
    marginBottom: 6,
  },
  proposalTitle: { fontSize: 13, fontWeight: '600', color: '#6b7280', marginBottom: 4 },
  proposalPrice: { fontSize: 22, fontWeight: '700', color: '#3f4a36', marginBottom: 8 },
  proposalBtnRow: { flexDirection: 'row', gap: 8 },
  proposalAcceptBtn: { flex: 1, backgroundColor: '#3f4a36', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  proposalDeclineBtn: { flex: 1, backgroundColor: '#fff', borderWidth: 1, borderColor: '#d1d5db', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  proposalAcceptText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  proposalDeclineText: { color: '#374151', fontWeight: '600', fontSize: 14 },
  proposalStatusText: { fontSize: 13, fontWeight: '600', marginTop: 4 },
});
