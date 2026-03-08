import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import * as DocumentPicker from 'expo-document-picker';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import api from '../src/api/api';

interface Document {
  id: number;
  filename: string;
  url: string;
}

export default function DocumentsScreen() {
  const { user } = useAuth();
  const { t } = useI18n();
  const isProvider = user?.role === 'provider';

  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const profileEndpoint = isProvider ? '/provider/profile' : '/client/profile';
  const deleteEndpoint = isProvider ? '/provider/delete_document' : '/client/delete_document';

  const loadDocuments = useCallback(async () => {
    try {
      const res = await api.get(profileEndpoint);
      setDocuments(res.data?.documents || []);
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [profileEndpoint]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadDocuments();
  };

  const handleUpload = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets?.length) {
        return;
      }

      const file = result.assets[0];
      setUploading(true);

      const formData = new FormData();
      formData.append('documents', {
        uri: file.uri,
        name: file.name,
        type: file.mimeType || 'application/octet-stream',
      } as any);

      await api.post(profileEndpoint, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      Alert.alert(t('success'), t('uploadDocument'));
      await loadDocuments();
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to upload document';
      Alert.alert(t('error'), msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = (doc: Document) => {
    Alert.alert(t('delete'), doc.filename, [
      { text: t('cancel'), style: 'cancel' },
      {
        text: t('delete'),
        style: 'destructive',
        onPress: async () => {
          setDeletingId(doc.id);
          try {
            await api.post(deleteEndpoint, { document_id: doc.id });
            setDocuments(prev => prev.filter(d => d.id !== doc.id));
          } catch (err: any) {
            const msg = err.response?.data?.msg || 'Failed to delete document';
            Alert.alert(t('error'), msg);
          } finally {
            setDeletingId(null);
          }
        },
      },
    ]);
  };

  const renderItem = ({ item }: { item: Document }) => (
    <View style={styles.documentRow}>
      <MaterialIcons name="insert-drive-file" size={24} color="#3f4a36" />
      <Text style={styles.documentName} numberOfLines={1}>
        {item.filename}
      </Text>
      {deletingId === item.id ? (
        <ActivityIndicator size="small" color="#ef4444" />
      ) : (
        <TouchableOpacity
          onPress={() => handleDelete(item)}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <MaterialIcons name="delete-outline" size={24} color="#ef4444" />
        </TouchableOpacity>
      )}
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <MaterialIcons name="folder-open" size={64} color="#d1d5db" />
      <Text style={styles.emptyText}>{t('noDocuments')}</Text>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: t('documents') }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <Stack.Screen options={{ headerShown: true, title: t('documents') }} />

      <FlatList
        data={documents}
        keyExtractor={item => String(item.id)}
        renderItem={renderItem}
        ListEmptyComponent={renderEmpty}
        contentContainerStyle={documents.length === 0 ? styles.emptyList : styles.listContent}
        refreshing={refreshing}
        onRefresh={handleRefresh}
      />

      {/* Upload FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={handleUpload}
        disabled={uploading}
        activeOpacity={0.7}
      >
        {uploading ? (
          <ActivityIndicator size="small" color="#fff" />
        ) : (
          <MaterialIcons name="cloud-upload" size={28} color="#fff" />
        )}
      </TouchableOpacity>
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
    paddingTop: 12,
    paddingBottom: 100,
  },
  emptyList: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 100,
  },
  emptyContainer: {
    alignItems: 'center',
    gap: 12,
  },
  emptyText: {
    fontSize: 16,
    color: '#9ca3af',
    fontWeight: '500',
  },
  documentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    gap: 12,
  },
  documentName: {
    flex: 1,
    fontSize: 15,
    fontWeight: '500',
    color: '#1f2937',
  },
  fab: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 40 : 24,
    right: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#3f4a36',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 6,
    elevation: 8,
  },
});
